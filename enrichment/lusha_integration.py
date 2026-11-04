import os
from dotenv import load_dotenv

load_dotenv()


class LushaClient:

    def __init__(self):

        self.api_key = os.getenv("LUSHA_API_KEY")

        if not self.api_key:
            raise ValueError(
                "LUSHA_API_KEY is missing. "
                "Add the company-provided API key to your .env file."
            )

    def find_contacts(self, company_name, website_url, designations):
        """
        Lusha contact search integration.

        Actual API request will be implemented after
        receiving Quiklee's Lusha API documentation.
        """

        raise NotImplementedError(
            "Lusha API endpoint and request format "
            "must be configured using official documentation."
        )


if __name__ == "__main__":

    try:
        client = LushaClient()
        print("Lusha API key detected.")
        print("Client initialized successfully.")

    except ValueError as error:
        print(error)