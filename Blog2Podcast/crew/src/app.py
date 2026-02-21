
import streamlit as st
from src.agent.blog2postcast_flow import kickoff


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
                output = kickoff(url=url)
                st.session_state["output"] = output

                st.subheader("📝 Blog Content")
                st.text_area("Content", output["blog_content"], height=300)

                st.subheader("📜 Podcast Script")
                print(output)
                st.text_area("Script", output["podcast_script"], height=300)

                if output["audio_file"]:
                    st.subheader("🔊 Podcast Audio")
                    audio_file = open(output["audio_file"], "rb")
                    st.audio(audio_file, format="audio/mp3")
            except Exception as e:
                st.error(f"❌ An error occurred: {e}")
