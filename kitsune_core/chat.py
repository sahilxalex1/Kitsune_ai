"""Kitsune chat subsystem. Extracted without changing the original function bodies."""

from .foundation import *
from .agent import *
from .agent_protocol import *
from .config import *
from .foundation import *
from .models import *
from .ollama import *
from .projects import *
from .web import *

def classify_message(user_input, model, config, usage_tracker):
    """Cheap, quiet, non-streamed call to decide: chat / search / code. Falls back to
    'chat' if the router itself fails or returns something unparseable -- never blocks
    the actual conversation on a routing hiccup."""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": ROUTER_SYSTEM_PROMPT},
            {"role": "user", "content": user_input},
        ],
        "stream": False,
        "format": "json",
        "options": {"num_ctx": config.get("context_window", 8192)},
    }
    try:
        r = requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=60)
        r.raise_for_status()
        data = r.json()
        usage_tracker.add(data.get("prompt_eval_count", 0), data.get("eval_count", 0))
        content = data.get("message", {}).get("content", "").strip()
        if content.startswith("```"):
            content = content.strip("`")
            if content.startswith("json"):
                content = content[4:]
            content = content.strip()
        return json.loads(content)
    except Exception:
        return {"category": "chat"}

def run_chat(config, usage_tracker, chat_model, router_model, available_models):
    chat_folder = os.getcwd()
    print("\nChat mode -- talk about anything. Type 'exit' or 'quit' to leave.")
    print(f"Working folder for any coding handoffs: {chat_folder}  (type 'cd <path>' to change it)")
    print("It'll automatically web-search when a question needs current info, and offer to")
    print("actually build/fix it in that folder when you're really asking for code.\n")
    messages = []
    while True:
        user_input = input("> ").strip()
        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit"):
            break
        if user_input.lower().startswith("cd "):
            candidate = os.path.abspath(user_input[3:].strip())
            if os.path.isdir(candidate):
                chat_folder = candidate
                print(f"Working folder set to: {chat_folder}")
            else:
                print(f"'{candidate}' isn't a directory.")
            continue

        route = classify_message(user_input, router_model, config, usage_tracker)
        category = route.get("category", "chat")

        if category == "code":
            suggested = route.get("suggested_goal", user_input)
            print(f"\nThat sounds like an actual coding task. Suggested goal:\n  \"{suggested}\"")
            ans = input(f"Build/fix this now in '{chat_folder}'? [y/N] ").strip().lower()
            if ans == "y":
                build_config = dict(config)
                build_config["model"] = model_for(config, "build_model")
                build_config["model"] = ensure_model_available(
                    build_config["model"], available_models, role="build_model", source="direct")
                new_root = resolve_new_project_folder(chat_folder, suggested)
                if new_root != chat_folder:
                    print(f"\n[Creating a new project folder for this: {new_root}]")
                ensure_config_file(new_root)
                run_agent(new_root, suggested, build_config, usage_tracker)
                messages.append({"role": "user", "content": user_input})
                messages.append({"role": "assistant", "content": f"(Handed off to the build agent in {new_root} for this.)"})
            else:
                print(f"OK -- you can also run:\n  kitsune.py build --dir \"{chat_folder}\" --goal \"{suggested}\"")
                print("(or 'fix' instead of 'build' if it's about fixing a bug in existing code)\n")
            continue

        messages.append({"role": "user", "content": user_input})

        if category == "search":
            query = route.get("search_query", user_input)
            print(f"\n[Searching: {query}]")
            result = do_web_search(query)
            print(result + "\n")
            messages.append({"role": "user", "content": f"Web search results for '{query}':\n{result}"})

        reply = ollama_chat_stream(CHAT_SYSTEM_PROMPT, messages, chat_model, config, usage_tracker, label="chat")
        messages.append({"role": "assistant", "content": reply})
    print("\n" + usage_tracker.summary())

