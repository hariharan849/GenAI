import logging
from typing import Optional

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from src.schemas.api.ask import AskRequest, AskResponse
from src.schemas.api.search import HybridSearchRequest

logger = logging.getLogger(__name__)


class TelegramBot:
    """Simple Telegram bot for Q&A."""

    def __init__(
        self,
        bot_token: str,
        opensearch_client,
        embeddings_client,
        ollama_client,
        cache_client=None,
    ):
        """Initialize bot with required services."""
        self.bot_token = bot_token
        self.opensearch = opensearch_client
        self.embeddings = embeddings_client
        self.ollama = ollama_client
        self.cache = cache_client
        self.application: Optional[Application] = None

    async def start(self) -> None:
        """Start the bot."""
        logger.info("Starting Telegram bot...")
        self.application = Application.builder().token(self.bot_token).build()

        # Register handlers
        self.application.add_handler(CommandHandler("start", self._start_command))
        self.application.add_handler(CommandHandler("help", self._help_command))
        self.application.add_handler(CommandHandler("search", self._search_command))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_question))

        # Start polling
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()
        logger.info("Telegram bot started successfully")

    async def stop(self) -> None:
        """Stop the bot."""
        if self.application:
            try:
                if self.application.updater.running:
                    await self.application.updater.stop()
            except Exception:
                pass
            await self.application.stop()
            await self.application.shutdown()
            logger.info("Telegram bot stopped")

    async def _start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command."""
        await update.message.reply_text(
            "Welcome to Nuke Documentation Assistant!\n\n"
            "Ask me questions about Foundry Nuke and I'll provide answers with sources.\n\n"
            "Commands:\n"
            "/help - Show this help\n"
            "/search <keywords> - Search documentation"
        )

    async def _help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /help command."""
        await update.message.reply_text(
            "Send me any question about Foundry Nuke VFX software.\n\n"
            "Examples:\n"
            "- How do I use the Blur node?\n"
            "- What is the Merge node?\n"
            "- How does color correction work in Nuke?\n\n"
            "Use /search to find specific documentation pages."
        )

    async def _search_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /search command."""
        if not context.args:
            await update.message.reply_text("Usage: /search <keywords>\nExample: /search neural networks")
            return

        query = " ".join(context.args)
        await update.message.chat.send_action("typing")

        try:
            # Generate embedding
            query_embedding = await self.embeddings.embed_query(query)

            # Search
            results = self.opensearch.search_unified(
                query=query,
                query_embedding=query_embedding,
                size=10,
                use_hybrid=True,
            )

            hits = results.get("hits", [])
            if not hits:
                await update.message.reply_text("No documentation found. Try different keywords.")
                return

            # Deduplicate by URL
            seen_urls = set()
            unique_pages = []
            for hit in hits:
                url = hit.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    unique_pages.append(hit)
                if len(unique_pages) >= 5:
                    break

            # Format results
            response = f"Found {len(unique_pages)} documentation pages:\n\n"
            for idx, hit in enumerate(unique_pages, 1):
                node_name = hit.get("nuke_node_name", hit.get("section", "Nuke Docs"))
                url = hit.get("url", "")
                response += f"{idx}. {node_name}\n{url}\n\n"

            await update.message.reply_text(response, disable_web_page_preview=True)

        except Exception as e:
            logger.error(f"Search failed: {e}", exc_info=True)
            await update.message.reply_text(f"Search failed: {str(e)}")

    async def _handle_question(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle user questions."""
        query = update.message.text
        await update.message.chat.send_action("typing")

        try:
            # Build request
            ask_request = AskRequest(query=query, top_k=3, use_hybrid=True)

            # Check cache
            if self.cache:
                try:
                    cached_response = await self.cache.find_cached_response(ask_request)
                    if cached_response:
                        await self._send_answer(update, cached_response)
                        return
                except Exception as e:
                    logger.warning(f"Cache lookup failed: {e}")

            # RAG pipeline
            from src.services.ollama.prompts import RAGPromptBuilder

            # Get embeddings if hybrid
            query_embedding = None
            if ask_request.use_hybrid:
                try:
                    query_embedding = await self.embeddings.embed_query(query)
                    logger.info("Generated query embedding")
                except Exception as e:
                    logger.warning(f"Failed to generate embeddings: {e}")

            # Search OpenSearch
            search_results = self.opensearch.search_unified(
                query=query,
                query_embedding=query_embedding,
                size=ask_request.top_k,
                use_hybrid=ask_request.use_hybrid and query_embedding is not None,
            )

            # Extract chunks and sources
            chunks = []
            sources_set = set()
            for hit in search_results.get("hits", []):
                chunks.append({"chunk_text": hit.get("chunk_text", "")})
                url = hit.get("url", "")
                if url:
                    sources_set.add(url)

            sources = list(sources_set)

            if not chunks:
                await update.message.reply_text("No relevant documentation found. Try rephrasing your question.")
                return

            # Generate answer
            prompt = RAGPromptBuilder().create_rag_prompt(query=query, chunks=chunks)
            ollama_response = await self.ollama.generate(model="llama3.2:1b", prompt=prompt, stream=False)
            answer = ollama_response.get("response", "") if ollama_response else ""

            # Build response
            response = AskResponse(
                query=query, answer=answer, sources=sources, chunks_used=len(chunks), search_mode="hybrid"
            )

            # Cache it
            if self.cache:
                try:
                    await self.cache.store_response(ask_request, response)
                except Exception:
                    pass

            # Send to user
            await self._send_answer(update, response)

        except Exception as e:
            logger.error(f"Question handling failed: {e}", exc_info=True)
            await update.message.reply_text(f"Error: {str(e)}")

    async def _send_answer(self, update: Update, response: AskResponse) -> None:
        """Send formatted answer to user."""
        # Answer
        message = f"*Answer:*\n{response.answer}\n"

        # Sources
        if response.sources:
            message += "\n*Sources:*\n"
            for idx, source_url in enumerate(response.sources[:5], 1):
                message += f"{idx}. {source_url}\n"

        # Send (try markdown, fallback to plain)
        try:
            await update.message.reply_text(message, parse_mode="Markdown", disable_web_page_preview=True)
        except Exception:
            await update.message.reply_text(message, disable_web_page_preview=True)
