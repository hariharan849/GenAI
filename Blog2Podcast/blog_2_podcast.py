import os, uuid

from langchain_groq import ChatGroq
from langgraph.graph import START, END, StateGraph
from langgraph.graph import MessagesState
from langchain_core.messages import SystemMessage, HumanMessage, RemoveMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END

import streamlit as st
from firecrawl import FirecrawlApp
from elevenlabs.client import ElevenLabs
from dotenv import load_dotenv
from typing import TypedDict

load_dotenv()


fire_crawl_api_key = os.environ.get("FIRECRAWL_API_KEY")
eleven_labs_api_key = os.environ.get("ELEVENLABS_API_KEY")
groq_api_key = os.environ.get("GROQ_API_KEY")


class BlogToPodcastState(TypedDict):
    url: str
    blog_content: str
    podcast_script: str
    audio_file: str

def scrape_blog_content_with_firecrawl(state):
    url = state.url if hasattr(state, "url") else state.get("url", "")
    if not fire_crawl_api_key:
        st.error("Firecrawl API key is missing. Please set the FIRECRAWL_API_KEY environment variable.")
        return {}
    client = FirecrawlApp(api_key=fire_crawl_api_key)
    response = client.scrape_url(url, formats=["markdown"], only_main_content=True)
    return {"blog_content": response.markdown}

def summarize_blog_content(state):
    blog_content = state.blog_content if hasattr(state, "blog_content") else state.get("blog_content", "")
    if not blog_content:
        st.error("No blog content to summarize.")
        return {}
    try:
        model = ChatGroq(
            model="llama-3.3-70b-versatile",
            api_key=groq_api_key,
            temperature=0.5,
            max_tokens=1000,
        )
        prompt = f"Summarize the following blog content and make it engaging and conversational:\n\n{blog_content}"
        response = model.invoke(prompt)
        return {"podcast_script": response.content.strip()}
    except Exception as e:
        st.error(f"Error summarizing blog content: {e}")
        return {}

def generate_audio(state):
    summary = state.podcast_script if hasattr(state, "podcast_script") else state.get("podcast_script", "")
    if not summary:
        st.error("No podcast script to convert to audio.")
        return {}
    client = ElevenLabs(api_key=eleven_labs_api_key)
    audio = client.text_to_speech.convert(
        voice_id="pNInz6obpgDQGcFmaJgB",  # Adam pre-made voice
        optimize_streaming_latency="0",
        output_format="mp3_22050_32",
        text=summary,
        model_id="eleven_multilingual_v2",
    )
    # Generating a unique file name for the output MP3 file
    save_file_path = f"{uuid.uuid4()}.mp3"
    # Writing the audio stream to the file

    with open(save_file_path, "wb") as f:
        for chunk in audio:
            if chunk:
                f.write(chunk)
    return {"audio_file": save_file_path}

graph = StateGraph(BlogToPodcastState)
graph.add_node("scrape", scrape_blog_content_with_firecrawl)
graph.add_node("summarize", summarize_blog_content)
graph.add_node("generate", generate_audio)
graph.add_edge("scrape", "summarize")
graph.add_edge("summarize", "generate")
graph.add_edge("generate", END)
graph.set_entry_point("scrape")
graph = graph.compile()


st.set_page_config(
    page_title="Blog to Podcast", page_icon=":microphone:", layout="wide"
)
st.markdown(
    "<h1 style='display: flex; align-items: center;'>"
    "<span style='font-size:2.5rem;margin-right:0.5rem;'>🎙️</span>"
    "Blog to Podcast"
    "</h1>",
    unsafe_allow_html=True,
)

url = st.text_input(
    "🔗 Enter the URL of the blog post you want to convert to a podcast",
    placeholder="https://example.com/blog-post",
    help="Enter the URL of the blog post you want to convert to a podcast",
)
generate_button = st.button("🚀 Generate Podcast")
if generate_button:
    if not url:
        st.error("❗ Please enter a valid URL.")
    else:
        with st.spinner("⏳ Scraping and generating podcast..."):
            try:
                state = BlogToPodcastState(url=url)
                output = graph.invoke(state)
                st.session_state["output"] = output

                st.subheader("📝 Blog Content")
                st.text_area("Content", output["blog_content"], height=300)

                st.subheader("📜 Podcast Script")
                st.text_area("Script", output["podcast_script"], height=300)

                if output["audio_file"]:
                    st.subheader("🔊 Podcast Audio")
                    audio_file = open(output["audio_file"], "rb")
                    st.audio(audio_file, format="audio/mp3")
            except Exception as e:
                st.error(f"❌ An error occurred: {e}")


##################################chat implementation#######################################################

model = ChatGroq(
    model="llama-3.3-70b-versatile",
    api_key=groq_api_key,
    temperature=0.5,
    max_tokens=1000,
)

class State(MessagesState):
    summary: str


# Define the logic to call the model
def call_model(state: State):
    
    # Get summary if it exists
    summary = state.get("summary", "")

    # If there is summary, then we add it
    if summary:
        
        # Add summary to system message
        system_message = f"Summary of conversation earlier: {summary}"

        # Append summary to any newer messages
        messages = [SystemMessage(content=system_message)] + state["messages"]
    
    else:
        messages = state["messages"]
    
    response = model.invoke(messages)
    return {"messages": response}

def summarize_conversation(state: State):
    
    # First, we get any existing summary
    summary = state.get("summary", "")

    # Create our summarization prompt 
    if summary:
        
        # A summary already exists
        summary_message = (
            f"This is summary of the conversation to date: {summary}\n\n"
            "Extend the summary by taking into account the new messages above:"
        )
        
    else:
        summary_message = "Create a summary of the conversation above:"

    # Add prompt to our history
    messages = state["messages"] + [HumanMessage(content=summary_message)]
    response = model.invoke(messages)
    
    # Delete all but the 2 most recent messages
    delete_messages = [RemoveMessage(id=m.id) for m in state["messages"][:-2]]
    return {"summary": response.content, "messages": delete_messages}

# Determine whether to end or summarize the conversation
def should_continue(state: State):
    
    """Return the next node to execute."""
    
    messages = state["messages"]
    
    # If there are more than six messages, then we summarize the conversation
    if len(messages) > 10:
        return "summarize_conversation"
    
    # Otherwise we can just end
    return END


if "output" in st.session_state and st.session_state["output"]:
    config = {"configurable": {"thread_id": "1"}}
    # RAG memory: store blog content for retrieval
    if "rag_memory" not in st.session_state:
        st.session_state["rag_memory"] = st.session_state["output"]["blog_content"]

    # Define a new graph
    workflow = StateGraph(State)
    workflow.add_node("conversation", call_model)
    workflow.add_node(summarize_conversation)

    # Set the entrypoint as conversation
    workflow.add_edge(START, "conversation")
    workflow.add_conditional_edges("conversation", should_continue)
    workflow.add_edge("summarize_conversation", END)

    # Compile
    memory = MemorySaver()
    graph = workflow.compile(checkpointer=memory)

    st.header("Chat with the Blog Content")
    # Ensure message history exists
    if "messages" not in st.session_state:
        st.session_state["messages"] = []

    # Display previous messages
    for message in st.session_state["messages"]:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Chat Input
    user_input = st.chat_input("Ask something about the blog content...")

    if user_input:
        blog_context = st.session_state["rag_memory"]
        # Compose messages for the LLM
        messages = [
            SystemMessage(content=f"You are an AI assistant. Use the following blog content as context to answer the user's questions:\n\n{blog_context}")
        ]
        # Add previous user/assistant messages to the context
        for msg in st.session_state["messages"]:
            if msg["role"] == "user":
                messages.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                messages.append(SystemMessage(content=msg["content"]))
        # Add the new user message
        messages.append(HumanMessage(content=user_input))
        # Add to session history for display
        st.session_state["messages"].append({"role": "user", "content": user_input})

        # Invoke the model with proper message objects, preserving history
        response = graph.invoke({"messages": messages}, config)
        ai_response = response['messages'][-1].content
        st.session_state["messages"].append({"role": "assistant", "content": ai_response})

        # Display AI Response
        with st.chat_message("assistant"):
            st.markdown(ai_response)

else:
    st.info("Please confirm the summary first before using the chatbot.")
