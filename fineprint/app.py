"""STEP 7 - THE APP: ask questions in the browser, see the evidence and what happened inside.
Run:  uv run streamlit run app.py
The app only calls ask() from step 4, so it uses exactly the pipeline you evaluated.
"""
import streamlit as st

from common import SOURCE, STRATEGY, TOP_K, MIN_SCORE
from step4_rag import GROUNDED, ask

st.set_page_config(page_title="FinePrint", layout="wide")
st.title("FinePrint")
st.caption(f"Reads the fine print of {SOURCE['bank']} current and savings accounts. Answers come only from the bank's "
           f"Key Facts Statement (retrieved {SOURCE['retrieved_on']}). Not financial advice.")

question = st.text_input("Your question", placeholder="Is there a fee to open an account?")
if question:
    with st.spinner("Searching the document and checking evidence..."):
        out = ask(question)

    answer_tab, xray_tab = st.tabs(["Answer", "RAG X-Ray"])
    with answer_tab:
        colour = "green" if out["state"] == GROUNDED else "orange"
        st.markdown(f"**Evidence state:** :{colour}[{out['state'].replace('_', ' ').title()}]")
        st.markdown(out["answer"])
        for i, c in enumerate(out["claims"], start=1):
            with st.expander(f"[{i}] {c['section']}"):
                st.markdown(f"> {c['excerpt']}")
                st.caption(f"{c['source']} · chunk {c['chunk_id']} · {c['url']}")
    with xray_tab:
        st.code(f"strategy={STRATEGY}  top_k={TOP_K}  min_score={MIN_SCORE}  time={out['seconds']:.2f}s")
        st.dataframe([{"rank": i, "chunk": h["chunk_id"], "section": h["section"], "score": round(h["score"], 3)}
                      for i, h in enumerate(out["hits"], start=1)], hide_index=True)
        if out.get("rejected"):
            st.warning(f"{len(out['rejected'])} citation(s) rejected: the quote was not in the cited chunk.")