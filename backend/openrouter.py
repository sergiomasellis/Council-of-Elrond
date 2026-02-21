"""OpenRouter API client for making LLM requests."""

import asyncio
import time
import httpx
from typing import List, Dict, Any, Optional
from .config import OPENROUTER_API_KEY, OPENROUTER_API_URL


def _estimate_tokens(text: str) -> int:
    """Estimate token count (~4 chars per token for English text)."""
    return max(1, len(text) // 4)


def _msgs_tokens(messages: list) -> int:
    """Estimate total tokens across a list of messages."""
    return sum(_estimate_tokens(m.get("content", "")) for m in messages)


async def query_model(
    model: str,
    messages: List[Dict[str, str]],
    timeout: float = 120.0
) -> Optional[Dict[str, Any]]:
    """
    Query a single model via OpenRouter API.

    Args:
        model: OpenRouter model identifier (e.g., "openai/gpt-4o")
        messages: List of message dicts with 'role' and 'content'
        timeout: Request timeout in seconds

    Returns:
        Response dict with 'content' and optional 'reasoning_details', or None if failed
    """
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": messages,
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                OPENROUTER_API_URL,
                headers=headers,
                json=payload
            )
            response.raise_for_status()

            data = response.json()
            message = data['choices'][0]['message']

            return {
                'content': message.get('content'),
                'reasoning_details': message.get('reasoning_details')
            }

    except Exception as e:
        print(f"Error querying model {model}: {e}")
        return None


async def query_models_parallel(
    models: List[str],
    messages: List[Dict[str, str]]
) -> Dict[str, Optional[Dict[str, Any]]]:
    """
    Query multiple models in parallel.

    Args:
        models: List of OpenRouter model identifiers
        messages: List of message dicts to send to each model

    Returns:
        Dict mapping model identifier to response dict (or None if failed)
    """
    import asyncio

    # Create tasks for all models
    tasks = [query_model(model, messages) for model in models]

    # Wait for all to complete
    responses = await asyncio.gather(*tasks)

    # Map models to their responses
    return {model: response for model, response in zip(models, responses)}


async def query_model_stream(
    model: str,
    messages: List[Dict[str, str]],
    timeout: float = 120.0,
    tools: Optional[List[Dict[str, Any]]] = None,
    tool_executor=None
):
    """
    Query a single model via OpenRouter API with streaming.
    Yields chunks of content.

    When tools and tool_executor are provided, handles tool-call loops
    internally — callers still receive only content chunks from the
    final response (after all tool use is complete). Intermediate
    preamble content (before tool calls) is NOT yielded.
    """
    import json

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:3000",
    }

    max_tool_rounds = 5
    tool_round_count = 0
    conversation = list(messages)
    t0 = time.time()

    def _log(msg: str):
        now = time.strftime("%H:%M:%S")
        elapsed = time.time() - t0
        print(f"  [{now} +{elapsed:5.1f}s] [{model}] {msg}")

    while True:
        # After exhausting tool rounds, stop offering tools to force a content response
        offer_tools = (
            tools if (tools and tool_executor and tool_round_count < max_tool_rounds)
            else None
        )
        is_final = not offer_tools

        request_messages = conversation
        if is_final and tool_round_count > 0:
            _log(f"Tool budget exhausted after {tool_round_count} rounds, requesting final answer...")
            # Add a user-role nudge so the model knows it must answer now.
            # Using "user" role because some providers ignore mid-conversation "system" messages.
            request_messages = conversation + [{
                "role": "user",
                "content": "[SYSTEM NOTE] Your tool/search budget is exhausted. You MUST now provide your final answer using the information you have already gathered. Do NOT request any more tools. Write your complete response now."
            }]

        payload = {
            "model": model,
            "messages": request_messages,
            "stream": True,
        }
        if offer_tools:
            payload["tools"] = offer_tools

        try:
            accumulated_content = ""
            tool_calls_by_index: Dict[int, Dict[str, Any]] = {}

            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream("POST", OPENROUTER_API_URL, headers=headers, json=payload) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            data_str = line[6:]
                            if data_str.strip() == "[DONE]":
                                break
                            try:
                                data = json.loads(data_str)
                                if 'choices' not in data or len(data['choices']) == 0:
                                    continue
                                choice = data['choices'][0]
                                delta = choice.get('delta', {})

                                # Accumulate content chunks
                                content = delta.get('content')
                                if content:
                                    accumulated_content += content
                                    # Only stream to caller on the final round
                                    if is_final:
                                        yield content

                                # Accumulate tool call deltas
                                if delta.get('tool_calls'):
                                    for tc_delta in delta['tool_calls']:
                                        idx = tc_delta.get('index', 0)
                                        if idx not in tool_calls_by_index:
                                            tool_calls_by_index[idx] = {
                                                'id': tc_delta.get('id', ''),
                                                'function': {
                                                    'name': '',
                                                    'arguments': ''
                                                }
                                            }
                                        tc = tool_calls_by_index[idx]
                                        if tc_delta.get('id'):
                                            tc['id'] = tc_delta['id']
                                        fn = tc_delta.get('function', {})
                                        if fn.get('name'):
                                            tc['function']['name'] += fn['name']
                                        if fn.get('arguments'):
                                            tc['function']['arguments'] += fn['arguments']

                            except json.JSONDecodeError:
                                continue

            # If no tool calls were accumulated, we're done
            if not tool_calls_by_index or not tool_executor:
                content_tokens = _estimate_tokens(accumulated_content) if accumulated_content else 0
                if not is_final and accumulated_content:
                    _log(f"Done (no tools used), content: ~{content_tokens} tokens")
                    yield accumulated_content
                elif is_final and accumulated_content:
                    _log(f"Done after {tool_round_count} tool rounds, content: ~{content_tokens} tokens")
                elif is_final and not accumulated_content and tool_round_count > 0:
                    _log(f"WARNING: No content after {tool_round_count} tool rounds — response will be empty")
                else:
                    _log(f"Done (no tools), content: ~{content_tokens} tokens")
                return

            # Process tool calls
            tool_round_count += 1
            sorted_calls = [tool_calls_by_index[i] for i in sorted(tool_calls_by_index.keys())]
            tool_names = [tc['function']['name'] for tc in sorted_calls]
            remaining = max_tool_rounds - tool_round_count
            _log(f"Tool calls (round {tool_round_count}/{max_tool_rounds}): {tool_names} — {remaining} rounds left")

            # Append assistant message with tool calls
            assistant_msg: Dict[str, Any] = {"role": "assistant"}
            if accumulated_content:
                assistant_msg["content"] = accumulated_content
            assistant_msg["tool_calls"] = [
                {
                    "id": tc['id'],
                    "type": "function",
                    "function": tc['function']
                }
                for tc in sorted_calls
            ]
            conversation.append(assistant_msg)

            # Execute all tool calls in parallel
            async def _exec_tool(tc):
                fn_name = tc['function']['name']
                fn_args = tc['function']['arguments']
                try:
                    args_preview = json.loads(fn_args) if fn_args else {}
                except json.JSONDecodeError:
                    args_preview = fn_args
                _log(f"  Executing {fn_name}({args_preview})")
                result = await tool_executor(fn_name, fn_args)
                result_tokens = _estimate_tokens(result) if result else 0
                _log(f"  {fn_name} → ~{result_tokens} tokens")
                return tc['id'], result

            results = await asyncio.gather(*[_exec_tool(tc) for tc in sorted_calls])
            for tool_call_id, result in results:
                conversation.append({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": result
                })

            conv_tokens = _msgs_tokens(conversation)
            _log(f"Round {tool_round_count} complete, sending back to model ({len(conversation)} msgs, ~{conv_tokens} tokens)")

            # Loop back for the next streaming request

        except Exception as e:
            msg_tokens = _msgs_tokens(request_messages)
            _log(f"ERROR on round {tool_round_count + (0 if offer_tools else 1)}: {e} ({len(request_messages)} msgs, ~{msg_tokens} tokens)")
            yield None
            return


async def query_models_stream(
    models: List[str],
    messages: List[Dict[str, str]],
    tools: Optional[List[Dict[str, Any]]] = None,
    tool_executor=None
):
    """
    Query multiple models in parallel with streaming.
    Yields (model, chunk) tuples.
    """
    import asyncio

    queue = asyncio.Queue()

    async def worker(model):
        try:
            async for chunk in query_model_stream(model, messages, tools=tools, tool_executor=tool_executor):
                if chunk is not None:
                    await queue.put((model, chunk))
        finally:
            await queue.put((model, None)) # Signal done for this model

    # Start workers
    tasks = [asyncio.create_task(worker(m)) for m in models]

    # Track active workers
    active_workers = len(models)

    while active_workers > 0:
        item = await queue.get()
        model, chunk = item
        if chunk is None:
            active_workers -= 1
        else:
            yield model, chunk

    # Cleanup tasks
    await asyncio.gather(*tasks)


async def query_models_stream_per_model(
    model_messages: Dict[str, List[Dict[str, str]]],
    tools: Optional[List[Dict[str, Any]]] = None,
    tool_executor=None
):
    """
    Query multiple models in parallel with streaming, each with its own messages.
    Yields (model, chunk) tuples.

    Args:
        model_messages: Dict mapping model identifier to its own message list
    """
    import asyncio

    queue = asyncio.Queue()

    async def worker(model, messages):
        try:
            async for chunk in query_model_stream(model, messages, tools=tools, tool_executor=tool_executor):
                if chunk is not None:
                    await queue.put((model, chunk))
        finally:
            await queue.put((model, None))

    tasks = [asyncio.create_task(worker(m, msgs)) for m, msgs in model_messages.items()]

    active_workers = len(model_messages)

    while active_workers > 0:
        item = await queue.get()
        model, chunk = item
        if chunk is None:
            active_workers -= 1
        else:
            yield model, chunk

    await asyncio.gather(*tasks)
