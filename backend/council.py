"""3-stage LLM Council orchestration."""

from typing import List, Dict, Any, Tuple
from .openrouter import query_models_parallel, query_model, query_model_stream, query_models_stream, query_models_stream_per_model
from .config import get_council_models, get_chairman_model
from .search import SEARCH_TOOLS, execute_search_tool


def build_stage1_history(
    prior_messages: List[Dict[str, Any]],
    current_query: str,
    models: List[str]
) -> Dict[str, List[Dict[str, str]]]:
    """
    Build per-model chat histories from conversation history.

    Each model gets its own prior responses as the assistant turns,
    with the council's chairman summary prefixed to subsequent user turns.
    Models not present in a prior turn get the chairman summary as their response.

    Returns:
        Dict mapping model identifier to its message list
    """
    model_messages: Dict[str, List[Dict[str, str]]] = {model: [] for model in models}

    # Extract (user, assistant) pairs from prior messages
    pairs = []
    i = 0
    while i < len(prior_messages) - 1:
        if prior_messages[i].get("role") == "user" and prior_messages[i + 1].get("role") == "assistant":
            pairs.append((prior_messages[i], prior_messages[i + 1]))
            i += 2
        else:
            i += 1

    prev_summary = ""
    for user_msg, assistant_msg in pairs:
        user_content = user_msg["content"]
        stage1_results = assistant_msg.get("stage1") or []
        stage3_result = assistant_msg.get("stage3") or {}
        chairman_summary = stage3_result.get("response", "")

        # Lookup table: model -> its own stage1 response
        stage1_by_model = {r["model"]: r["response"] for r in stage1_results}

        for model in models:
            # Prefix user message with previous turn's chairman summary
            if prev_summary:
                content = f"[Council's synthesized answer]\n{prev_summary}\n\n{user_content}"
            else:
                content = user_content
            model_messages[model].append({"role": "user", "content": content})

            # Model's own response, or chairman summary as fallback
            model_response = stage1_by_model.get(model, chairman_summary)
            model_messages[model].append({"role": "assistant", "content": model_response or ""})

        prev_summary = chairman_summary

    # Append the current query as the final user message
    for model in models:
        if prev_summary:
            content = f"[Council's synthesized answer]\n{prev_summary}\n\n{current_query}"
        else:
            content = current_query
        model_messages[model].append({"role": "user", "content": content})

    return model_messages


def build_stage3_history(
    prior_messages: List[Dict[str, Any]]
) -> List[Dict[str, str]]:
    """
    Build chairman chat history from prior conversation turns.

    Returns alternating user/assistant messages with user questions
    and chairman summaries.
    """
    history: List[Dict[str, str]] = []

    i = 0
    while i < len(prior_messages) - 1:
        if prior_messages[i].get("role") == "user" and prior_messages[i + 1].get("role") == "assistant":
            user_msg = prior_messages[i]
            assistant_msg = prior_messages[i + 1]

            stage3_result = assistant_msg.get("stage3") or {}
            chairman_summary = stage3_result.get("response", "")

            history.append({"role": "user", "content": user_msg["content"]})
            if chairman_summary:
                history.append({"role": "assistant", "content": chairman_summary})

            i += 2
        else:
            i += 1

    return history


async def stage1_collect_responses(user_query: str) -> List[Dict[str, Any]]:
    """
    Stage 1: Collect individual responses from all council models.

    Args:
        user_query: The user's question

    Returns:
        List of dicts with 'model' and 'response' keys
    """
    council_models = get_council_models()
    messages = [{"role": "user", "content": user_query}]

    # Query all models in parallel
    responses = await query_models_parallel(council_models, messages)

    # Format results
    stage1_results = []
    for model, response in responses.items():
        if response is not None:  # Only include successful responses
            stage1_results.append({
                "model": model,
                "response": response.get('content', '')
            })

    return stage1_results


async def stage1_collect_responses_stream(user_query: str, conversation_history=None):
    """
    Stage 1: Collect individual responses from all council models (Streaming).
    Yields (model, chunk) tuples.

    Args:
        user_query: The user's question
        conversation_history: Optional list of prior messages for multi-turn context
    """
    council_models = get_council_models()
    if conversation_history:
        model_messages = build_stage1_history(conversation_history, user_query, council_models)
        async for model, chunk in query_models_stream_per_model(model_messages, tools=SEARCH_TOOLS, tool_executor=execute_search_tool):
            yield model, chunk
    else:
        messages = [{"role": "user", "content": user_query}]
        async for model, chunk in query_models_stream(council_models, messages, tools=SEARCH_TOOLS, tool_executor=execute_search_tool):
            yield model, chunk


async def stage2_collect_rankings(
    user_query: str,
    stage1_results: List[Dict[str, Any]]
) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    """
    Stage 2: Each model ranks the anonymized responses.

    Args:
        user_query: The original user query
        stage1_results: Results from Stage 1

    Returns:
        Tuple of (rankings list, label_to_model mapping)
    """
    # Create anonymized labels for responses (Response A, Response B, etc.)
    labels = [chr(65 + i) for i in range(len(stage1_results))]  # A, B, C, ...

    # Create mapping from label to model name
    label_to_model = {
        f"Response {label}": result['model']
        for label, result in zip(labels, stage1_results)
    }

    # Build the ranking prompt
    responses_text = "\n\n".join([
        f"Response {label}:\n{result['response']}"
        for label, result in zip(labels, stage1_results)
    ])

    ranking_prompt = f"""You are evaluating different responses to the following question:

Question: {user_query}

Here are the responses from different models (anonymized):

{responses_text}

Your task:
1. First, evaluate each response individually. For each response, explain what it does well and what it does poorly.
2. Then, at the very end of your response, provide a final ranking.

IMPORTANT: Your final ranking MUST be formatted EXACTLY as follows:
- Start with the line "FINAL RANKING:" (all caps, with colon)
- Then list the responses from best to worst as a numbered list
- Each line should be: number, period, space, then ONLY the response label (e.g., "1. Response A")
- Do not add any other text or explanations in the ranking section

Example of the correct format for your ENTIRE response:

Response A provides good detail on X but misses Y...
Response B is accurate but lacks depth on Z...
Response C offers the most comprehensive answer...

FINAL RANKING:
1. Response C
2. Response A
3. Response B

Now provide your evaluation and ranking:"""

    messages = [{"role": "user", "content": ranking_prompt}]

    # Get rankings from all council models in parallel
    council_models = get_council_models()
    responses = await query_models_parallel(council_models, messages)

    # Format results
    stage2_results = []
    for model, response in responses.items():
        if response is not None:
            full_text = response.get('content', '')
            parsed = parse_ranking_from_text(full_text)
            stage2_results.append({
                "model": model,
                "ranking": full_text,
                "parsed_ranking": parsed
            })

    return stage2_results, label_to_model


async def stage2_collect_rankings_stream(
    user_query: str,
    stage1_results: List[Dict[str, Any]]
):
    """
    Stage 2: Each model ranks the anonymized responses (Streaming).
    Yields (model, chunk, label_to_model) tuples.
    """
    # Create anonymized labels for responses (Response A, Response B, etc.)
    labels = [chr(65 + i) for i in range(len(stage1_results))]  # A, B, C, ...

    # Create mapping from label to model name
    label_to_model = {
        f"Response {label}": result['model']
        for label, result in zip(labels, stage1_results)
    }

    # Build the ranking prompt
    responses_text = "\n\n".join([
        f"Response {label}:\n{result['response']}"
        for label, result in zip(labels, stage1_results)
    ])

    ranking_prompt = f"""You are evaluating different responses to the following question:

Question: {user_query}

Here are the responses from different models (anonymized):

{responses_text}

Your task:
1. First, evaluate each response individually. For each response, explain what it does well and what it does poorly.
2. Then, at the very end of your response, provide a final ranking.

IMPORTANT: Your final ranking MUST be formatted EXACTLY as follows:
- Start with the line "FINAL RANKING:" (all caps, with colon)
- Then list the responses from best to worst as a numbered list
- Each line should be: number, period, space, then ONLY the response label (e.g., "1. Response A")
- Do not add any other text or explanations in the ranking section

Example of the correct format for your ENTIRE response:

Response A provides good detail on X but misses Y...
Response B is accurate but lacks depth on Z...
Response C offers the most comprehensive answer...

FINAL RANKING:
1. Response C
2. Response A
3. Response B

Now provide your evaluation and ranking:"""

    messages = [{"role": "user", "content": ranking_prompt}]

    # Yield label_to_model first so frontend knows the mapping
    yield None, None, label_to_model

    # Query all models in parallel with streaming
    council_models = get_council_models()
    async for model, chunk in query_models_stream(council_models, messages):
        yield model, chunk, None


async def stage3_synthesize_final(
    user_query: str,
    stage1_results: List[Dict[str, Any]],
    stage2_results: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Stage 3: Chairman synthesizes final response.

    Args:
        user_query: The original user query
        stage1_results: Individual model responses from Stage 1
        stage2_results: Rankings from Stage 2

    Returns:
        Dict with 'model' and 'response' keys
    """
    # Build comprehensive context for chairman
    stage1_text = "\n\n".join([
        f"Model: {result['model']}\nResponse: {result['response']}"
        for result in stage1_results
    ])

    stage2_text = "\n\n".join([
        f"Model: {result['model']}\nRanking: {result['ranking']}"
        for result in stage2_results
    ])

    chairman_prompt = f"""You are the Chairman of an LLM Council. Multiple AI models have provided responses to a user's question, and then ranked each other's responses.

Original Question: {user_query}

STAGE 1 - Individual Responses:
{stage1_text}

STAGE 2 - Peer Rankings:
{stage2_text}

Your task as Chairman is to synthesize all of this information into a single, comprehensive, accurate answer to the user's original question. Consider:
- The individual responses and their insights
- The peer rankings and what they reveal about response quality
- Any patterns of agreement or disagreement

Provide a clear, well-reasoned final answer that represents the council's collective wisdom:"""

    chairman_model = get_chairman_model()
    messages = [{"role": "user", "content": chairman_prompt}]

    # Query the chairman model
    response = await query_model(chairman_model, messages)

    if response is None:
        # Fallback if chairman fails
        return {
            "model": chairman_model,
            "response": "Error: Unable to generate final synthesis."
        }

    return {
        "model": chairman_model,
        "response": response.get('content', '')
    }


async def stage3_synthesize_final_stream(
    user_query: str,
    stage1_results: List[Dict[str, Any]],
    stage2_results: List[Dict[str, Any]],
    conversation_history=None
):
    """
    Stage 3: Chairman synthesizes final response (Streaming).
    Yields chunks of the response.

    Args:
        user_query: The user's question
        stage1_results: Individual model responses from Stage 1
        stage2_results: Rankings from Stage 2
        conversation_history: Optional list of prior messages for multi-turn context
    """
    # Build comprehensive context for chairman
    stage1_text = "\n\n".join([
        f"Model: {result['model']}\nResponse: {result['response']}"
        for result in stage1_results
    ])

    stage2_text = "\n\n".join([
        f"Model: {result['model']}\nRanking: {result['ranking']}"
        for result in stage2_results
    ])

    chairman_prompt = f"""You are the Chairman of an LLM Council. Multiple AI models have provided responses to a user's question, and then ranked each other's responses.

Original Question: {user_query}

STAGE 1 - Individual Responses:
{stage1_text}

STAGE 2 - Peer Rankings:
{stage2_text}

Your task as Chairman is to synthesize all of this information into a single, comprehensive, accurate answer to the user's original question. Consider:
- The individual responses and their insights
- The peer rankings and what they reveal about response quality
- Any patterns of agreement or disagreement

Provide a clear, well-reasoned final answer that represents the council's collective wisdom:"""

    chairman_model = get_chairman_model()

    if conversation_history:
        history = build_stage3_history(conversation_history)
        messages = history + [{"role": "user", "content": chairman_prompt}]
    else:
        messages = [{"role": "user", "content": chairman_prompt}]

    # Yield the model info first
    yield {
        "type": "model_info",
        "model": chairman_model
    }

    # Stream the response
    full_response = ""
    async for chunk in query_model_stream(chairman_model, messages, tools=SEARCH_TOOLS, tool_executor=execute_search_tool):
        if chunk:
            full_response += chunk
            yield {
                "type": "content_chunk",
                "chunk": chunk
            }

    # Yield the final complete object
    yield {
        "type": "complete",
        "data": {
            "model": chairman_model,
            "response": full_response
        }
    }


def parse_ranking_from_text(ranking_text: str) -> List[str]:
    """
    Parse the FINAL RANKING section from the model's response.

    Args:
        ranking_text: The full text response from the model

    Returns:
        List of response labels in ranked order
    """
    import re

    # Look for "FINAL RANKING:" section
    if "FINAL RANKING:" in ranking_text:
        # Extract everything after "FINAL RANKING:"
        parts = ranking_text.split("FINAL RANKING:")
        if len(parts) >= 2:
            ranking_section = parts[1]
            # Try to extract numbered list format (e.g., "1. Response A")
            # This pattern looks for: number, period, optional space, "Response X"
            numbered_matches = re.findall(r'\d+\.\s*Response [A-Z]', ranking_section)
            if numbered_matches:
                # Extract just the "Response X" part
                return [re.search(r'Response [A-Z]', m).group() for m in numbered_matches]

            # Fallback: Extract all "Response X" patterns in order
            matches = re.findall(r'Response [A-Z]', ranking_section)
            return matches

    # Fallback: try to find any "Response X" patterns in order
    matches = re.findall(r'Response [A-Z]', ranking_text)
    return matches


def calculate_aggregate_rankings(
    stage2_results: List[Dict[str, Any]],
    label_to_model: Dict[str, str]
) -> List[Dict[str, Any]]:
    """
    Calculate aggregate rankings across all models.

    Args:
        stage2_results: Rankings from each model
        label_to_model: Mapping from anonymous labels to model names

    Returns:
        List of dicts with model name and average rank, sorted best to worst
    """
    from collections import defaultdict

    # Track positions for each model
    model_positions = defaultdict(list)

    for ranking in stage2_results:
        ranking_text = ranking['ranking']

        # Parse the ranking from the structured format
        parsed_ranking = parse_ranking_from_text(ranking_text)

        for position, label in enumerate(parsed_ranking, start=1):
            if label in label_to_model:
                model_name = label_to_model[label]
                model_positions[model_name].append(position)

    # Calculate average position for each model
    aggregate = []
    for model, positions in model_positions.items():
        if positions:
            avg_rank = sum(positions) / len(positions)
            aggregate.append({
                "model": model,
                "average_rank": round(avg_rank, 2),
                "rankings_count": len(positions)
            })

    # Sort by average rank (lower is better)
    aggregate.sort(key=lambda x: x['average_rank'])

    return aggregate


async def generate_conversation_title(user_query: str) -> str:
    """
    Generate a short title for a conversation based on the first user message.

    Args:
        user_query: The first user message

    Returns:
        A short title (3-5 words)
    """
    title_prompt = f"""Generate a very short title (3-5 words maximum) that summarizes the following question.
The title should be concise and descriptive. Do not use quotes or punctuation in the title.

Question: {user_query}

Title:"""

    messages = [{"role": "user", "content": title_prompt}]

    # Use gemini-2.5-flash for title generation (fast and cheap)
    response = await query_model("google/gemini-2.5-flash", messages, timeout=30.0)

    if response is None:
        # Fallback to a generic title
        return "New Conversation"

    title = response.get('content', 'New Conversation').strip()

    # Clean up the title - remove quotes, limit length
    title = title.strip('"\'')

    # Truncate if too long
    if len(title) > 50:
        title = title[:47] + "..."

    return title


async def run_full_council(user_query: str) -> Tuple[List, List, Dict, Dict]:
    """
    Run the complete 3-stage council process.

    Args:
        user_query: The user's question

    Returns:
        Tuple of (stage1_results, stage2_results, stage3_result, metadata)
    """
    # Stage 1: Collect individual responses
    stage1_results = await stage1_collect_responses(user_query)

    # If no models responded successfully, return error
    if not stage1_results:
        return [], [], {
            "model": "error",
            "response": "All models failed to respond. Please try again."
        }, {}

    # Stage 2: Collect rankings
    stage2_results, label_to_model = await stage2_collect_rankings(user_query, stage1_results)

    # Calculate aggregate rankings
    aggregate_rankings = calculate_aggregate_rankings(stage2_results, label_to_model)

    # Stage 3: Synthesize final answer
    stage3_result = await stage3_synthesize_final(
        user_query,
        stage1_results,
        stage2_results
    )

    # Prepare metadata
    metadata = {
        "label_to_model": label_to_model,
        "aggregate_rankings": aggregate_rankings
    }

    return stage1_results, stage2_results, stage3_result, metadata
