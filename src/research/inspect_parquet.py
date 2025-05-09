import pandas as pd

# load the file
df = pd.read_parquet("edgar_labels.parquet")

# see the first few rows
print(df.head())

# get a quick summary of the label distribution
print(df["sentiment_label_3d"].value_counts())

# inspect column types and non-null counts
print(df.info())

# export the DataFrame to a CSV file
df.to_csv("edgar_labels.csv", index=False)