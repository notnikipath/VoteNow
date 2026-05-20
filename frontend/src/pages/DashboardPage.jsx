import React, { useEffect, useMemo, useState } from "react";

import { MetricCard } from "../components/MetricCard";
import { QuestionField } from "../components/QuestionField";

const gatewayUrl = (import.meta.env.VITE_API_GATEWAY_URL || "http://localhost:32082").replace(/\/+$/, "");

async function request(path, method = "GET", payload) {
  const options = { method, headers: { "Content-Type": "application/json" } };
  if (payload) {
    options.body = JSON.stringify(payload);
  }
  const response = await fetch(`${gatewayUrl}${path}`, options);
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}

export function DashboardPage() {
  const [token, setToken] = useState("demo-votenow");
  const [dashboard, setDashboard] = useState(null);
  const [status, setStatus] = useState("loading");
  const [error, setError] = useState(null);
  const [respondentId, setRespondentId] = useState("student-001");
  const [email, setEmail] = useState("");
  const [verificationCode, setVerificationCode] = useState("");
  const [answers, setAnswers] = useState({});

  const survey = dashboard?.survey;

  async function reload() {
    setStatus("loading");
    try {
      const payload = await request(`/dashboard/public/${token}`);
      setDashboard(payload);
      setStatus("ready");
      setError(null);
    } catch (err) {
      setStatus("error");
      setError(err.message);
    }
  }

  useEffect(() => {
    reload();
  }, [token]);

  const chartCards = useMemo(() => {
    return (dashboard?.charts?.charts || []).slice(0, 4);
  }, [dashboard]);

  async function submitSurvey(event) {
    event.preventDefault();
    if (!survey) {
      return;
    }

    const payload = {
      survey_id: survey.survey_id,
      answers: Object.entries(answers).map(([question_id, value]) => ({ question_id, value })),
      captcha_token: "ok",
      verification_code: verificationCode || null,
      respondent: {
        respondent_id: respondentId || null,
        email: email || null,
        ip_address: "127.0.0.1",
        user_agent: "votenow-frontend",
      },
    };

    try {
      await request("/workflow/submit-response", "POST", payload);
      setVerificationCode("");
      await reload();
    } catch (err) {
      setError(err.message);
      setStatus("error");
    }
  }

  return (
    <div className="page-shell">
      <header className="hero">
        <p className="tag">VoteNow Live Platform</p>
        <h1>Public surveys, anti-fraud response collection, verification, and real-time results.</h1>
        <div className="hero-controls">
          <input value={token} onChange={(event) => setToken(event.target.value)} placeholder="Public token" />
          <button onClick={reload}>Refresh</button>
        </div>
      </header>

      <section className="metrics-grid">
        <MetricCard
          title="Responses"
          value={dashboard?.live?.total_responses ?? 0}
          hint="Current participation"
        />
        <MetricCard
          title="Last Minute"
          value={dashboard?.live?.responses_last_minute ?? 0}
          hint="Real-time throughput"
        />
        <MetricCard
          title="Projected"
          value={dashboard?.live?.projected_responses ?? 0}
          hint="Forecast until close"
        />
        <MetricCard
          title="Length Advice"
          value={dashboard?.live?.question_count ?? 0}
          hint={dashboard?.live?.length_recommendation || "No recommendation"}
        />
      </section>

      {error ? <div className="error-box">{error}</div> : null}

      <main className="content-grid">
        <form className="survey-card" onSubmit={submitSurvey}>
          <h2>{survey?.title || "Survey"}</h2>
          <p>{survey?.description}</p>

          <label>
            Respondent ID
            <input value={respondentId} onChange={(event) => setRespondentId(event.target.value)} placeholder="student-001" />
          </label>
          <label>
            Email (optional)
            <input value={email} onChange={(event) => setEmail(event.target.value)} placeholder="name@example.com" />
          </label>
          <label>
            Verification code (if enabled)
            <input value={verificationCode} onChange={(event) => setVerificationCode(event.target.value)} placeholder="123456" />
          </label>

          {(survey?.questions || []).map((question) => (
            <QuestionField
              key={question.question_id}
              question={question}
              value={answers[question.question_id]}
              onChange={(value) => setAnswers((prev) => ({ ...prev, [question.question_id]: value }))}
            />
          ))}

          <button type="submit" disabled={status === "loading"}>
            Submit response
          </button>
        </form>

        <section className="results-card">
          <h2>Live Results</h2>
          <p>
            Throughput status: {dashboard?.live?.throughput_ok ? "within target" : "above target"}
          </p>
          <div className="chart-list">
            {chartCards.map((chart) => (
              <article className="chart-item" key={chart.question_id}>
                <h3>{chart.title}</h3>
                {chart.kind === "gauge" ? (
                  <p className="gauge">Average: {chart.avg}</p>
                ) : (
                  <ul>
                    {(chart.labels || []).map((label, index) => (
                      <li key={label}>
                        <span>{label}</span>
                        <strong>{chart.values?.[index] ?? 0}</strong>
                      </li>
                    ))}
                  </ul>
                )}
              </article>
            ))}
          </div>
        </section>
      </main>
    </div>
  );
}
