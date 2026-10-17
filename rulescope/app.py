"""STEP 10 - APP: a web page to ask RuleScope questions and see how each answer was built.
Run:  uv run streamlit run app.py

Tabs
  Answer    the verified answer, numbered citations, the exact quotes, links to the official Rulebook pages
  Audit Trail every stage of the pipeline: audience, the 20 candidates and their scores, the 5 the reranker kept,
            what validation dropped or repaired, and how long each stage took
"""
import pandas as pd
import streamlit as st

from common import ATTRIBUTION, DISCLAIMER, DOC_BY_ID, DOCS, MIN_SCORE, REFUSAL, STRATEGY, USE_RERANKER
from step4_rag import answer

EXAMPLES = [
    "When must a bank give a customer the Key Facts Statement?",
    "When does a bank account become dormant?",
    "What hours are banks allowed to make telemarketing calls?",
    "What must a bank disclose to an SME before it signs a facility agreement?",
    "Which UAE bank has the best credit card rewards?",            # shows a refusal
]

st.set_page_config(page_title="RuleScope", page_icon="📘", layout="wide")

# ---------- sidebar: scope, examples, how it works ----------
with st.sidebar:
    st.header("Scope")
    titles = {d["doc_id"]: d["title"] for d in DOCS}
    chosen = st.multiselect("Search these regulations", options=list(titles), default=list(titles),
                            format_func=lambda doc_id: titles[doc_id])
    st.caption(f"{len(chosen)} of {len(titles)} regulations selected")

    st.header("Try an example")
    for example in EXAMPLES:
        if st.button(example, width="stretch"):
            st.session_state["question"] = example

    with st.expander("How RuleScope works"):
        st.markdown(
            "1. **Retrieve** the 20 most similar passages (Pinecone)\n"
            "2. **Gate**: refuse if nothing is close enough\n"
            "3. **Rerank**: keep the 5 that best answer the question\n"
            "4. **Generate**: the model writes claims, each with a source and a quote\n"
            "5. **Validate**: code checks every quote is really in the cited passage\n\n"
            "A question about SMEs only searches SME rules; any other question never sees them.")
        st.caption(f"Settings: {STRATEGY} chunks · reranker {'on' if USE_RERANKER else 'off'} · "
                   f"refusal gate {MIN_SCORE}")

# ---------- header ----------
st.title("RuleScope")
st.write("Ask questions about UAE Central Bank consumer-protection and retail-banking regulations. "
         "Every answer is built only from the regulation text, with the article and an exact quote for each point.")
st.info(DISCLAIMER, icon="ℹ️")

question = st.text_input("Your question", key="question",
                         placeholder="e.g. How long before signing must I receive the Key Facts Statement?")
ask = st.button("Ask", type="primary")

if (ask or st.session_state.get("last_question") != question) and question.strip():
    if not chosen:
        st.warning("Select at least one regulation in the sidebar.")
        st.stop()
    with st.spinner("Searching the regulations and checking every quote..."):
        doc_ids = None if len(chosen) == len(titles) else chosen
        st.session_state["result"] = answer(question.strip(), doc_ids=doc_ids)
        st.session_state["last_question"] = question

result = st.session_state.get("result")
if result:
    tab_answer, tab_audit = st.tabs(["Answer", "Audit Trail"])

    # ---------- Answer tab ----------
    with tab_answer:
        if result["refused"]:
            st.warning(REFUSAL)
            st.caption(f"Why: {result['refusal_reason']}. Try rephrasing, or check the regulations selected in the sidebar.")
        else:
            st.markdown(result["answer"])
            st.subheader("Sources")
            for c in result["citations"]:
                doc = DOC_BY_ID.get(c["doc_id"], {})
                details = " · ".join(x for x in (c["reference"], f"effective {doc.get('effective')}"
                                                  if doc.get("effective") else "") if x)
                st.markdown(f"**[{c['n']}] {c['where']}**" + (f"  \n<small>{details}</small>" if details else ""),
                            unsafe_allow_html=True)
                for quote in c["quotes"]:
                    st.markdown(f"> {quote}")
                if c["page_url"]:
                    st.markdown(f"[Open the official Rulebook page]({c['page_url']})")
        st.divider()
        st.caption(ATTRIBUTION + " RuleScope is an independent project and is not affiliated with the Central Bank of the UAE.")

    # ---------- Audit Trail tab ----------
    with tab_audit:
        t = result["timings"]
        cols = st.columns(5)
        cols[0].metric("Audience", result.get("audience", "-"))
        cols[1].metric("Retrieve", f"{t.get('retrieve', 0):.1f}s")
        cols[2].metric("Rerank", f"{t.get('rerank', 0):.1f}s")
        cols[3].metric("Generate", f"{t.get('generate', 0):.1f}s")
        cols[4].metric("Total", f"{t.get('total', 0):.1f}s")

        st.subheader("1. Retrieved candidates")
        kept = {s["meta"]["chunk_id"]: s for s in result["sources"]}
        table = pd.DataFrame([{
            "rank": i,
            "similarity": round(c["similarity"], 3),
            "regulation": c["meta"]["title"],
            "article": c["meta"]["article"],
            "sub-section": c["meta"].get("section", ""),
            "kept by reranker": kept[c["meta"]["chunk_id"]]["label"] if c["meta"]["chunk_id"] in kept else "",
            "rerank score": round(kept[c["meta"]["chunk_id"]].get("rerank_score", 0), 3)
                            if c["meta"]["chunk_id"] in kept else None,
        } for i, c in enumerate(result["candidates"], start=1)])
        best = table["similarity"].max() if not table.empty else 0
        st.caption(f"Best similarity {best:.3f} · refusal gate {MIN_SCORE} → "
                   f"{'passed' if best >= MIN_SCORE else 'refused here'}")
        st.dataframe(table, hide_index=True, width="stretch")

        if result["sources"]:
            st.subheader("2. Passages given to the model")
            for s in result["sources"]:
                with st.expander(f"{s['label']} · {s['meta']['title']} · {s['meta']['article']}"):
                    st.text(s["text"])

        if result["claims"]:
            st.subheader("3. Validation")
            st.write(f"The model wrote **{len(result['claims'])}** claims; "
                     f"**{len(result['answer'].splitlines()) if not result['refused'] else 0}** passed the quote check.")
            for note in result["notes"]:
                st.write(f"- {note}")
            if not result["notes"]:
                st.write("Every quote matched its cited passage exactly.")