# 🎹 Turn Blogs into Podcasts Using AI: LangChain, Firecrawl & ElevenLabs

**Credits**:

* [Awesome LLM Apps by Shubham Saboo](https://github.com/Shubhamsaboo/awesome-llm-apps/tree/main/starter_ai_agents/ai_blog_to_podcast_agent)
* [LangGraph Chatbot with Summarization](https://academy.langchain.com/courses/take/intro-to-langgraph/lessons/58239436-lesson-5-chatbot-w-summarizing-messages-and-memory)

Ever wish you could **listen to your favorite blog posts** while walking, driving, or multitasking? Even better, what if you could **chat with the blog content itself**?

In this tutorial, you'll build an end-to-end pipeline that:

* Scrapes any blog post from the web
* Summarizes it using a powerful language model (LLaMA 3 via Groq)
* Converts the summary into realistic audio using ElevenLabs
* Lets you interactively chat with the content
* All wrapped in a clean Streamlit UI

---

## 🛠️ Prerequisites

Install the necessary dependencies:

```bash
pip install streamlit python-dotenv firecrawl elevenlabs langchain langchain_groq
```

---

## 1. 📦 Define the State Schema

We'll use `TypedDict` to define the state schema that travels between nodes in LangGraph.

```python
class BlogToPodcastState(TypedDict):
    url: str
    blog_content: str
    podcast_script: str
    audio_file: str
```

This enables clear structure and typing as we transition data between scraping, summarization, and audio generation stages.

---

## 2. 🔍 Scrape Blog Content using Firecrawl

Firecrawl is a powerful tool for scraping **clean main content** from any webpage. It saves you from manually parsing HTML.

```python
def scrape_blog_content_with_firecrawl(state):
    url = state.url if hasattr(state, "url") else state.get("url", "")
    if not fire_crawl_api_key:
        st.error("Firecrawl API key is missing. Please set the FIRECRAWL_API_KEY environment variable.")
        return {}
    client = FirecrawlApp(api_key=fire_crawl_api_key)
    response = client.scrape_url(url, formats=["markdown"], only_main_content=True)
    return {"blog_content": response.markdown}
```

---

## 3. ✍️ Summarize Blog Content with Groq + LangChain

Use Groq (an ultra-fast inference engine) with the `llama-3.3-70b-versatile` model to generate a conversational and engaging summary.

```python
def summarize_blog_content(state):
    blog_content = state.blog_content if hasattr(state, "blog_content") else state.get("blog_content", "")
    if not blog_content:
        st.error("No blog content to summarize.")
        return {}
    model = ChatGroq(
        model="llama-3.3-70b-versatile",
        api_key=groq_api_key,
        temperature=0.5,
        max_tokens=1000,
    )
    prompt = f"Summarize the following blog content and make it engaging and conversational:\n\n{blog_content}"
    response = model.invoke(prompt)
    return {"podcast_script": response.content.strip()}
```

---

## 4. 🔊 Generate Natural Voice Audio with ElevenLabs

Convert the summary text into audio using ElevenLabs' lifelike voice generation API.

```python
def generate_audio(state):
    summary = state.podcast_script if hasattr(state, "podcast_script") else state.get("podcast_script", "")
    if not summary:
        st.error("No podcast script to convert to audio.")
        return {}
    client = ElevenLabs(api_key=eleven_labs_api_key)
    audio = client.text_to_speech.convert(
        voice_id="pNInz6obpgDQGcFmaJgB",  # Adam voice
        optimize_streaming_latency="0",
        output_format="mp3_22050_32",
        text=summary,
        model_id="eleven_multilingual_v2",
    )
    save_file_path = f"{uuid.uuid4()}.mp3"
    with open(save_file_path, "wb") as f:
        for chunk in audio:
            if chunk:
                f.write(chunk)
    return {"audio_file": save_file_path}
```

---

## 5. ⚖️ LangGraph Flow: Connecting the Pipeline

Create a stateful flow using LangGraph's `StateGraph`:

```python
graph = StateGraph(BlogToPodcastState)
graph.add_node("scrape", scrape_blog_content_with_firecrawl)
graph.add_node("summarize", summarize_blog_content)
graph.add_node("generate", generate_audio)
graph.add_edge("scrape", "summarize")
graph.add_edge("summarize", "generate")
graph.add_edge("generate", END)
graph.set_entry_point("scrape")
graph = graph.compile()
```

---

## 6. 🌐 Streamlit Frontend: Launch the App

```python
st.set_page_config(page_title="Blog to Podcast", page_icon=":microphone:", layout="wide")
st.markdown("""
<h1 style='display: flex; align-items: center;'>
<span style='font-size:2.5rem;margin-right:0.5rem;'>🎧</span>
Blog to Podcast
</h1>
""", unsafe_allow_html=True)

url = st.text_input("🔗 Enter the URL of the blog post")
generate_button = st.button("🚀 Generate Podcast")
if generate_button and url:
    with st.spinner("⌛ Scraping and generating podcast..."):
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
```

---

## 🧠 Chat with the Blog Content

Now let’s build a chatbot that lets you interact with the blog content.

### 1. Define State

```python
class State(MessagesState):
    summary: str
```

### 2. Chat Model Invocation Logic

```python
def call_model(state: State):
    summary = state.get("summary", "")
    messages = [SystemMessage(content=f"Summary: {summary}")] + state["messages"] if summary else state["messages"]
    response = model.invoke(messages)
    return {"messages": response}
```

### 3. Summarize Conversation Logic

```python
def summarize_conversation(state: State):
    summary = state.get("summary", "")
    summary_prompt = f"This is summary of the conversation to date: {summary}\n\nExtend the summary:" if summary else "Create a summary of the conversation above:"
    messages = state["messages"] + [HumanMessage(content=summary_prompt)]
    response = model.invoke(messages)
    delete_messages = [RemoveMessage(id=m.id) for m in state["messages"][:-2]]
    return {"summary": response.content, "messages": delete_messages}
```

### 4. Routing Logic

```python
def should_continue(state: State):
    return "summarize_conversation" if len(state["messages"]) > 10 else END
```

### 5. LangGraph Chatbot Flow

```python
workflow = StateGraph(State)
workflow.add_node("conversation", call_model)
workflow.add_node("summarize_conversation", summarize_conversation)
workflow.add_edge(START, "conversation")
workflow.add_conditional_edges("conversation", should_continue)
workflow.add_edge("summarize_conversation", END)
graph = workflow.compile(checkpointer=MemorySaver())
```

### 6. Streamlit Chat UI

```python
st.header("Chat with the Blog Content")
if "messages" not in st.session_state:
    st.session_state["messages"] = []

for message in st.session_state["messages"]:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

user_input = st.chat_input("Ask something about the blog content...")

if user_input:
    blog_context = st.session_state["rag_memory"]
    messages = [SystemMessage(content=f"Use this blog content to help you answer:\n\n{blog_context}")]
    for msg in st.session_state["messages"]:
        role = msg["role"]
        content = msg["content"]
        messages.append(HumanMessage(content=content) if role == "user" else SystemMessage(content=content))
    messages.append(HumanMessage(content=user_input))
    st.session_state["messages"].append({"role": "user", "content": user_input})

    response = graph.invoke({"messages": messages}, config={"configurable": {"thread_id": "1"}})
    ai_response = response['messages'][-1].content
    st.session_state["messages"].append({"role": "assistant", "content": ai_response})

    with st.chat_message("assistant"):
        st.markdown(ai_response)
```

---

## 🚀 You're All Set!

You now have a working app that:

* Scrapes a blog post
* Summarizes it into a script
* Converts that script into podcast audio
* Lets users chat with the content

Perfect for newsletters, blogs, podcasts, or internal knowledge tools.

Enjoy building!
