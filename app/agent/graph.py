"""The chat workflow as a LangGraph state graph.

START ─▶ classify_question
           ├─ direct ─▶ direct_answer ─▶ END
           └─ rag ────▶ retrieve_documents
                          ├─ relevant passages ─▶ generate_grounded_answer ─▶ validate_answer
                          │                                                     ├─ passed ─▶ END
                          │                                                     └─ failed ─▶ fallback_response ─▶ END
                          ├─ weak, route was only a guess ─▶ direct_answer ─▶ END
                          └─ weak ─▶ fallback_response ─▶ END
"""

from langgraph.graph import END, START, StateGraph

from app.agent.nodes import (
    classify_question,
    direct_answer,
    fallback_response,
    generate_grounded_answer,
    retrieve_documents,
    validate_answer,
)
from app.agent.state import ChatState


def route_after_classify(state: ChatState) -> str:
    return "retrieve_documents" if state["route"] == "rag" else "direct_answer"


def route_after_retrieval(state: ChatState) -> str:
    if not state["plan"].fallback:
        return "generate_grounded_answer"
    # Weak retrieval. If the document route was only a default guess, the
    # question probably isn't about the documents - answer it directly instead.
    if state.get("routed_by") == "default":
        return "direct_answer"
    return "fallback_response"


def route_after_validation(state: ChatState) -> str:
    return "fallback_response" if state.get("validation_error") else END


def build_graph():
    graph = StateGraph(ChatState)

    graph.add_node("classify_question", classify_question)
    graph.add_node("direct_answer", direct_answer)
    graph.add_node("retrieve_documents", retrieve_documents)
    graph.add_node("generate_grounded_answer", generate_grounded_answer)
    graph.add_node("validate_answer", validate_answer)
    graph.add_node("fallback_response", fallback_response)

    graph.add_edge(START, "classify_question")
    graph.add_conditional_edges(
        "classify_question", route_after_classify, ["direct_answer", "retrieve_documents"]
    )
    graph.add_conditional_edges(
        "retrieve_documents",
        route_after_retrieval,
        ["generate_grounded_answer", "direct_answer", "fallback_response"],
    )
    graph.add_edge("generate_grounded_answer", "validate_answer")
    graph.add_conditional_edges(
        "validate_answer", route_after_validation, ["fallback_response", END]
    )
    graph.add_edge("direct_answer", END)
    graph.add_edge("fallback_response", END)

    return graph.compile()


chat_graph = build_graph()
