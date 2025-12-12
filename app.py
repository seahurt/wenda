import json
import uuid
import random
from collections import Counter
from difflib import SequenceMatcher
from typing import List, Dict

from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

QUESTIONS: Dict[str, Dict[str, List[str]]] = {}


def normalize_text(text: str) -> str:
    """Normalize text for similarity comparison."""
    return " ".join(text.strip().lower().split())


def validate_payload(payload: List[Dict]) -> List[Dict]:
    """Validate uploaded question payload and return sanitized data."""
    sanitized = []
    if not isinstance(payload, list):
        raise ValueError("JSON root must be a list of questions")

    for idx, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Question {idx} must be an object with 'ask' and 'answer' keys")
        ask = item.get("ask")
        answer = item.get("answer")
        if not isinstance(ask, str) or not ask.strip():
            raise ValueError(f"Question {idx} has an invalid 'ask' value")
        if not isinstance(answer, list) or not answer:
            raise ValueError(f"Question {idx} must include a non-empty 'answer' list")
        if not all(isinstance(step, str) and step.strip() for step in answer):
            raise ValueError(f"Question {idx} answer steps must all be non-empty strings")
        sanitized.append({"ask": ask.strip(), "answer": [step.strip() for step in answer]})
    return sanitized


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/api/upload", methods=["POST"])
def upload_questions():
    if "file" not in request.files:
        return jsonify({"error": "Missing file in request"}), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "No file selected"}), 400

    try:
        payload = json.load(file)
        sanitized = validate_payload(payload)
    except (ValueError, json.JSONDecodeError) as exc:
        return jsonify({"error": f"Invalid file format: {exc}"}), 400

    global QUESTIONS
    QUESTIONS = {}
    for item in sanitized:
        question_id = str(uuid.uuid4())
        QUESTIONS[question_id] = {"ask": item["ask"], "answer": item["answer"]}

    return jsonify({"message": "Upload successful", "total": len(QUESTIONS)})


@app.route("/api/random")
def random_questions():
    if not QUESTIONS:
        return jsonify({"error": "No questions uploaded yet"}), 400

    try:
        requested = int(request.args.get("n", 5))
    except ValueError:
        return jsonify({"error": "Parameter 'n' must be an integer"}), 400

    requested = max(1, requested)
    selection = random.sample(list(QUESTIONS.items()), k=min(requested, len(QUESTIONS)))

    response = []
    for qid, question in selection:
        steps = question["answer"]
        shuffled = steps.copy()
        random.shuffle(shuffled)
        response.append(
            {
                "id": qid,
                "ask": question["ask"],
                "steps_shuffled": shuffled,
                "step_count": len(steps),
            }
        )

    return jsonify({"questions": response, "available": len(QUESTIONS)})


@app.route("/api/submit_manual", methods=["POST"])
def submit_manual():
    data = request.get_json(force=True, silent=True) or {}
    qid = data.get("id")
    user_response = data.get("response", "")
    threshold = data.get("threshold", 0.6)

    if qid not in QUESTIONS:
        return jsonify({"error": "Unknown question id"}), 400

    try:
        threshold_val = float(threshold)
    except (TypeError, ValueError):
        return jsonify({"error": "Threshold must be a number"}), 400

    if not 0 <= threshold_val <= 1:
        return jsonify({"error": "Threshold must be between 0 and 1"}), 400

    correct_answer = " ".join(QUESTIONS[qid]["answer"])
    ratio = SequenceMatcher(None, normalize_text(user_response), normalize_text(correct_answer)).ratio()
    is_correct = ratio >= threshold_val

    return jsonify({
        "correct": is_correct,
        "similarity": round(ratio, 3),
        "threshold": threshold_val,
        "expected": correct_answer,
    })


@app.route("/api/submit_order", methods=["POST"])
def submit_order():
    data = request.get_json(force=True, silent=True) or {}
    qid = data.get("id")
    ordered_steps = data.get("ordered_steps")

    if qid not in QUESTIONS:
        return jsonify({"error": "Unknown question id"}), 400

    if not isinstance(ordered_steps, list) or not all(isinstance(step, str) for step in ordered_steps):
        return jsonify({"error": "ordered_steps must be a list of strings"}), 400

    correct_steps = QUESTIONS[qid]["answer"]
    if Counter(ordered_steps) != Counter(correct_steps):
        return jsonify({"error": "Provided steps do not match the original options"}), 400

    is_correct = ordered_steps == correct_steps
    return jsonify({"correct": is_correct, "expected": correct_steps})


if __name__ == "__main__":
    app.run(debug=True)
