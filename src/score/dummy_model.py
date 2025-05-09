import re
import random

class DummySentimentModel:
    """
    A baseline dummy sentiment model that uses simple keyword matching.
    It's packaged as a class with a .predict() method as per APP-3.2.
    """
    MODEL_VERSION = "dummy_heuristic_v0.2"

    def __init__(self):
        # Define some positive and negative keywords
        # These are very basic and for demonstration purposes
        self.positive_keywords = [
            "strong", "growth", "profit", "achieved", "success", "positive",
            "increase", "benefit", "opportunity", "improvement", "launch"
        ]
        self.negative_keywords = [
            "loss", "decline", "weak", "challenging", "risk", "negative",
            "decrease", "impairment", "failure", "issue", "concern"
        ]

        # Compile regex patterns for efficiency
        self.positive_pattern = re.compile(r'\b(' + '|'.join(self.positive_keywords) + r')\b', re.IGNORECASE)
        self.negative_pattern = re.compile(r'\b(' + '|'.join(self.negative_keywords) + r')\b', re.IGNORECASE)

    def predict(self, text: str) -> float:
        """
        Predicts a sentiment score for the given text.
        Score is between -1.0 (very negative) and 1.0 (very positive).
        """
        if not isinstance(text, str):
            # Handle cases where text might not be a string (e.g. None from failed S3 fetch)
            return 0.0 

        positive_matches = len(self.positive_pattern.findall(text))
        negative_matches = len(self.negative_pattern.findall(text))

        if positive_matches > negative_matches:
            # More positive keywords, lean positive
            # Add some randomness to simulate a more complex model's variance
            return random.uniform(0.3, 0.8)
        elif negative_matches > positive_matches:
            # More negative keywords, lean negative
            return random.uniform(-0.8, -0.3)
        elif positive_matches > 0: # Equal non-zero matches
             return random.uniform(-0.2, 0.2) # Slightly neutral but acknowledge content
        else:
            # No strong keywords found, or equal number of matches
            # Return a score closer to neutral, with slight randomness
            return random.uniform(-0.1, 0.1)

    def get_model_version(self) -> str:
        return self.MODEL_VERSION

if __name__ == '__main__':
    # Example usage:
    model = DummySentimentModel()
    
    text1 = "The company reported strong growth and profit."
    score1 = model.predict(text1)
    print(f"Text: '{text1}'\nScore: {score1:.2f}\n")

    text2 = "There are significant risks and challenging market conditions."
    score2 = model.predict(text2)
    print(f"Text: '{text2}'\nScore: {score2:.2f}\n")

    text3 = "The product launch was a success, but we see some concerns." # Mixed
    score3 = model.predict(text3)
    print(f"Text: '{text3}'\nScore: {score3:.2f}\n")

    text4 = "This document contains no relevant financial information." # Neutral
    score4 = model.predict(text4)
    print(f"Text: '{text4}'\nScore: {score4:.2f}\n")
