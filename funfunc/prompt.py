from openai import AsyncOpenAI
import urllib.parse

class GPTSearchPrompt:
    def __init__(self, api_key, model_chat):
        self.client = AsyncOpenAI(api_key=api_key)
        self.model_chat = model_chat

    async def generate_search_query(self, topic):
        """
        Generate a search query using GPT based on the provided topic.
        """
        try:
            prompt_message = f"Provide a concise Google search term for: {topic}."
            chat_completion = await self.client.chat.completions.create(
                model=self.model_chat,
                messages=[{"role": "user", "content": prompt_message}]
            )
            return chat_completion.choices[0].message.content.strip() if chat_completion.choices else None
        except Exception as e:
            print(f"Error in generate_search_query: {e}")
            return None

    @staticmethod
    def construct_google_search_url(search_query):
        """
        Construct a Google search URL based on the search query.
        """
        base_url = "https://www.google.com/search"
        query_param = urllib.parse.urlencode({"q": search_query})
        return f"{base_url}?{query_param}"

