from sklearn.feature_extraction.text import CountVectorizer
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import make_pipeline

# 1. Sample training data
texts = [
    "I love this movie",       # Positive
    "This film was great",     # Positive
    "Amazing experience",      # Positive
    "I hate this movie",       # Negative
    "Terrible and boring",     # Negative
    "Worst film ever",         # Negative
]

labels = [1, 1, 1, 0, 0, 0]  # 1 = Positive, 0 = Negative

# 2. Create a model: Vectorizer + Classifier

# A vectorizer is a tool that converts text into numbers,
# because machine learning models can’t understand raw text — they need numerical data to work.

model = make_pipeline(CountVectorizer(), MultinomialNB())

# The pipeline combines the vectorizer and the classifier into a single model that can be trained and used for predictions.
# The CountVectorizer converts text to a matrix of token counts,
# and the MultinomialNB classifier is used for classification.

# 3. Train the model
model.fit(texts, labels)

# 4. Test the model with new text
test_text = [
    "I didn't like the film",
    "What a boring movie",
    "I really enjoyed it",
    "It was a fantastic performance",
    "I did not like it",
    "I enjoyed the movie",
]

# 5. Predict
predictions = model.predict(test_text)

# 6. Show results
for text, label in zip(test_text, predictions):
    sentiment = "Positive" if label == 1 else "Negative"
    print(f"'{text}' → {sentiment}")
