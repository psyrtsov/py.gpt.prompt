"""
pygptprompt/api/openai.py
"""
import sys
from typing import Iterator, List, Tuple, Union

import openai
from llama_cpp import ChatCompletionChunk, ChatCompletionMessage, EmbeddingData

from pygptprompt import logging
from pygptprompt.api.base import BaseAPI
from pygptprompt.api.types import ExtendedChatCompletionMessage
from pygptprompt.config.manager import ConfigurationManager


class OpenAIAPI(BaseAPI):
    """
    API class for interacting with the OpenAI language models.

    Args:
        config (ConfigurationManager): The configuration manager instance.

    Attributes:
        config (ConfigurationManager): The configuration manager instance.
    """

    def __init__(self, config: ConfigurationManager):
        """
        Initialize the OpenAIAPI class.

        Args:
            config (ConfigurationManager): The configuration manager instance.
        """
        self.config = config
        openai.api_key = config.get_api_key()

    def _extract_content(self, delta: dict, content: str) -> str:
        """
        Extracts content from the given delta and appends it to the existing content.

        Args:
            delta (dict): The delta object containing new content.
            content (str): The existing content.

        Returns:
            str: The updated content after appending the new token.
        """
        if delta and "content" in delta and delta["content"]:
            token = delta["content"]
            print(token, end="")
            sys.stdout.flush()
            content += token
        return content

    def _extract_function_call(
        self,
        delta: dict,
        function_call_name: str,
        function_call_args: str,
    ) -> Tuple[str, str]:
        """
        Extracts function call information from the given delta and updates the function call name and arguments.

        Args:
            delta (dict): The delta object containing function call information.
            function_call_name (str): The existing function call name.
            function_call_args (str): The existing function call arguments.

        Returns:
            Tuple[str, str]: A tuple containing the updated function call name and arguments.
        """
        if delta and "function_call" in delta and delta["function_call"]:
            function_call = delta["function_call"]
            if not function_call_name:
                function_call_name = function_call.get("name", "")
            function_call_args += str(function_call.get("arguments", ""))
        return function_call_name, function_call_args

    def _handle_finish_reason(
        self,
        finish_reason: str,
        function_call_name: str,
        function_call_args: str,
        content: str,
    ) -> ExtendedChatCompletionMessage:
        """
        Handles the finish reason and returns an ExtendedChatCompletionMessage.

        Args:
            finish_reason (str): The finish reason from the response.
            function_call_name (str): The function call name.
            function_call_args (str): The function call arguments.
            content (str): The generated content.

        Returns:
            ExtendedChatCompletionMessage: An ExtendedChatCompletionMessage object with relevant information.
        """
        if finish_reason:
            if finish_reason == "function_call":
                return ExtendedChatCompletionMessage(
                    role="function",
                    function_call=function_call_name,
                    function_args=function_call_args,
                )
            elif finish_reason == "stop":
                print()  # Add newline to model output
                sys.stdout.flush()
                return ExtendedChatCompletionMessage(role="assistant", content=content)
            else:
                # Handle unexpected finish_reason
                raise ValueError(f"Warning: Unexpected finish_reason '{finish_reason}'")

    def _stream_chat_completion(
        self, response_generator: Iterator[ChatCompletionChunk]
    ) -> ExtendedChatCompletionMessage:
        """
        Streams the chat completion response and handles the content and function call information.

        Args:
            response_generator (Iterator[ChatCompletionChunk]): An iterator of ChatCompletionChunk objects.

        Returns:
            ExtendedChatCompletionMessage: An ExtendedChatCompletionMessage object with relevant information.
        """
        function_call_name = None
        function_call_args = ""
        content = ""

        for chunk in response_generator:
            delta = chunk["choices"][0]["delta"]

            content = self._extract_content(delta, content)
            function_call_name, function_call_args = self._extract_function_call(
                delta, function_call_name, function_call_args
            )

            finish_reason = chunk["choices"][0]["finish_reason"]
            message = self._handle_finish_reason(
                finish_reason, function_call_name, function_call_args, content
            )

            if message:
                return message

    def get_completions(self, prompt: str):
        """
        Get completions from the OpenAI language models.

        Raises:
            NotImplementedError: This method is not implemented in the OpenAIAPI class.
        """
        raise NotImplementedError

    def get_chat_completions(
        self,
        messages: List[ChatCompletionMessage],
    ) -> ChatCompletionMessage:
        """
        Generate chat completions using the OpenAI language models.

        Args:
            messages (List[ChatCompletionMessage]): The list of chat completion messages.

        Returns:
            ChatCompletionMessage: The generated chat completion message.
        """
        if not messages:
            raise ValueError("'messages' argument cannot be empty or None")

        try:
            # Call the OpenAI API's /v1/chat/completions endpoint
            response = openai.ChatCompletion.create(
                messages=messages,
                functions=self.config.get_value("function.definitions", []),
                function_call=self.config.get_value("function.call", "auto"),
                model=self.config.get_value(
                    "openai.chat_completions.model", "gpt-3.5-turbo"
                ),
                temperature=self.config.get_value(
                    "openai.chat_completions.temperature", 0.8
                ),
                max_tokens=self.config.get_value(
                    "openai.chat_completions.max_tokens", 1024
                ),
                top_p=self.config.get_value("openai.chat_completions.top_p", 0.95),
                n=self.config.get_value("openai.chat_completions.n", 1),
                stop=self.config.get_value("openai.chat_completions.stop", []),
                presence_penalty=self.config.get_value(
                    "openai.chat_completions.presence_penalty", 0
                ),
                frequency_penalty=self.config.get_value(
                    "openai.chat_completions.frequency_penalty", 0
                ),
                logit_bias=self.config.get_value(
                    "openai.chat_completions.logit_bias", {}
                ),
                stream=True,  # NOTE: Always coerce streaming
            )
            return self._stream_chat_completion(response)
        except Exception as e:
            logging.error(f"Error generating chat completions: {e}")
            return ChatCompletionMessage(role="error", content=str(e))

    def get_embeddings(self, input: Union[str, list[str]]) -> EmbeddingData:
        """
        Generate embeddings using the OpenAI language models.

        Args:
            input (Union[str, list[str]]): The input text or list of texts to generate embeddings for.

        Returns:
            EmbeddingData: The generated embedding vector.
        """
        if not input:
            raise ValueError("'input' argument cannot be empty or None")

        try:
            # Call the OpenAI API's /v1/embeddings endpoint
            response = openai.Embedding.create(
                input=input,
                model=self.config.get_value(
                    "openai.embedding.model", "text-embedding-ada-002"
                ),
            )
            return EmbeddingData(**response["data"][0])
        except Exception as e:
            logging.error(f"Error generating embeddings: {e}")
            return EmbeddingData(index=0, object="list", embedding=[])
