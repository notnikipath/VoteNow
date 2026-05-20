import React from "react";

function CheckboxOption({ option, selected, onToggle }) {
  return (
    <label className="option-line">
      <input type="checkbox" checked={selected} onChange={() => onToggle(option)} />
      <span>{option}</span>
    </label>
  );
}

export function QuestionField({ question, value, onChange }) {
  if (question.question_type === "single_choice") {
    return (
      <div className="question-block">
        <p className="question-title">{question.title}</p>
        <div className="option-list">
          {question.options.map((option) => (
            <label className="option-line" key={option}>
              <input
                type="radio"
                name={question.question_id}
                checked={value === option}
                onChange={() => onChange(option)}
              />
              <span>{option}</span>
            </label>
          ))}
        </div>
      </div>
    );
  }

  if (question.question_type === "multiple_choice") {
    const selected = Array.isArray(value) ? value : [];
    return (
      <div className="question-block">
        <p className="question-title">{question.title}</p>
        <div className="option-list">
          {question.options.map((option) => (
            <CheckboxOption
              key={option}
              option={option}
              selected={selected.includes(option)}
              onToggle={(current) => {
                if (selected.includes(current)) {
                  onChange(selected.filter((item) => item !== current));
                  return;
                }
                onChange([...selected, current]);
              }}
            />
          ))}
        </div>
      </div>
    );
  }

  if (question.question_type === "rating") {
    return (
      <div className="question-block">
        <p className="question-title">{question.title}</p>
        <label className="rating-line">
          <input
            type="range"
            min={question.rating_min}
            max={question.rating_max}
            step={question.rating_step}
            value={value ?? question.rating_min}
            onChange={(event) => onChange(Number(event.target.value))}
          />
          <strong>{value ?? question.rating_min}</strong>
        </label>
      </div>
    );
  }

  if (question.question_type === "open_text") {
    return (
      <div className="question-block">
        <p className="question-title">{question.title}</p>
        <textarea
          rows={4}
          value={value || ""}
          onChange={(event) => onChange(event.target.value)}
          placeholder="Write your answer"
        />
      </div>
    );
  }

  return (
    <div className="question-block">
      <p className="question-title">{question.title}</p>
      <select value={value || ""} onChange={(event) => onChange(event.target.value)}>
        <option value="">Choose winner</option>
        {question.options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    </div>
  );
}
