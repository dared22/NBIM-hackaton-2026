import numpy as np
import pandas as pd
from sklearn.datasets import make_classification
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score, accuracy_score

# 1. Import EBM classes and the visualizer from interpret-ml
from interpret.glassbox import ExplainableBoostingClassifier
from interpret import show

# ---------------------------------------------------------
# Step 1: Create a Dummy Dataset
# ---------------------------------------------------------
# Creating a mock tabular dataset with informative features
X_raw, y_raw = make_classification(
    n_samples=1000, 
    n_features=4, 
    n_informative=3, 
    random_state=42
)

feature_names = ["Age", "Savings_Rate", "Credit_Score", "Employment_Type"]
df = pd.DataFrame(X_raw, columns=feature_names)

# Convert one numeric column into a categorical string feature to show EBM handles both natively
df["Employment_Type"] = pd.qcut(df["Employment_Type"], q=3, labels=["Unemployed", "Self-Employed", "Salaried"])
df["Employment_Type"] = df["Employment_Type"].astype(str)

X = df
y = y_raw

# Split into training and testing sets
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

# ---------------------------------------------------------
# Step 2: Initialize and Fit the EBM Model
# ---------------------------------------------------------
# EBM automatically handles missing values and text/categorical categorical data.
ebm = ExplainableBoostingClassifier(
    interactions=2,      # Automatically search and include 2-way feature interactions
    random_state=42
)
ebm.fit(X_train, y_train)

# ---------------------------------------------------------
# Step 3: Evaluate Model Performance
# ---------------------------------------------------------
y_pred = ebm.predict(X_test)
y_proba = ebm.predict_proba(X_test)[:, 1]

print(f"Test Accuracy: {accuracy_score(y_test, y_pred):.3f}")
print(f"Test AUC Score: {roc_auc_score(y_test, y_proba):.3f}")

# ---------------------------------------------------------
# Step 4: Extract and Visualize Explanations
# ---------------------------------------------------------

# A. Global Explanation (What did the model learn across the entire dataset?)
ebm_global = ebm.explain_global()

# B. Local Explanation (Why did the model make a specific prediction for row index 0?)
ebm_local = ebm.explain_local(X_test.iloc[0:1], y_test[0:1])

# C. Launch the Interactive Dashboard 
# This opens an interactive tab in your browser or an inline widget if using Jupyter Notebooks.
show([ebm_global, ebm_local])
