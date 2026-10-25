from __future__ import annotations

import streamlit as st
from src.conversation import new_state, respond

st.set_page_config(page_title="ZentroMart Support Assistant", page_icon="🛍️")
st.title("ZentroMart Support Assistant")
st.caption("Course capstone prototype · synthetic training dataset · do not enter real personal or order information")

if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "Hi, I’m ZentroMart’s AI support assistant. How can I help you today?"}]
if "conversation" not in st.session_state:
    st.session_state.conversation = new_state()

with st.sidebar:
    st.subheader("Prototype status")
    st.write("Policy retrieval, verified synthetic order lookup, and ticketed human handoff are enabled. Order details stay hidden until verification succeeds.")
    st.caption("Data reference date: 20 October 2026")
    if st.button("Start a new conversation"):
        st.session_state.messages = [{"role": "assistant", "content": "Hi, I’m ZentroMart’s AI support assistant. How can I help you today?"}]
        st.session_state.conversation = new_state()
        st.rerun()

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("evidence"):
            st.caption("Sources: " + ", ".join(msg["evidence"]))

if prompt := st.chat_input("Type your question (use synthetic examples only)"):
    with st.spinner("Checking your request..."):
        result = respond(prompt, st.session_state.conversation)
    displayed_user = result.get("user_display", prompt)
    st.session_state.messages.append({"role": "user", "content": displayed_user})
    with st.chat_message("user"):
        st.markdown(displayed_user)
    with st.chat_message("assistant"):
        st.markdown(result["answer"])
        if result["evidence"]:
            st.caption("Sources: " + ", ".join(result["evidence"]))
    st.session_state.messages.append({"role": "assistant", "content": result["answer"], "evidence": result["evidence"]})

