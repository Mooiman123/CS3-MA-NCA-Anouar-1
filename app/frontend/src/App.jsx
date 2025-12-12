import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  createEmployee,
  listEmployees,
  updateEmployee,
  deleteEmployee,
  login as loginRequest,
  setAuthEmail as setApiAuthEmail,
} from "./api";
import "./style.css";

const emptyForm = { name: "", email: "", department: "" };
const initialLoginForm = {
  email: "anouar@innovatech.com",
  password: "",
};

export default function App() {
  const [authUser, setAuthUser] = useState(() => {
    const raw = sessionStorage.getItem("authUser");
    return raw ? JSON.parse(raw) : null;
  });
  const [isAuthenticated, setIsAuthenticated] = useState(() => !!authUser);
  const [authStatus, setAuthStatus] = useState(null);
  const [loginForm, setLoginForm] = useState(initialLoginForm);
  const [authSubmitting, setAuthSubmitting] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(false);
  const [employees, setEmployees] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  const selectedEmployee = useMemo(
    () => employees.find((e) => e.employeeId === selectedId) || null,
    [employees, selectedId]
  );

  const fetchEmployees = useCallback(async () => {
    if (!isAuthenticated) {
      return;
    }
    try {
      setLoading(true);
      const res = await listEmployees();
      setEmployees(res.data || []);
    } catch (err) {
      setStatus({ ok: false, msg: "Kon lijst niet laden." });
    } finally {
      setLoading(false);
    }
  }, [isAuthenticated]);

  useEffect(() => {
    if (authUser?.email) {
      setApiAuthEmail(authUser.email);
      setIsAuthenticated(true);
      fetchEmployees();
    } else {
      setApiAuthEmail(null);
      setIsAuthenticated(false);
      setEmployees([]);
    }
  }, [authUser, fetchEmployees]);

  const handleLoginSubmit = async (e) => {
    e.preventDefault();
    setAuthStatus(null);
    setAuthSubmitting(true);
    try {
      const response = await loginRequest(loginForm);
      const { email, name } = response.data || {};
      if (!email) {
        throw new Error("Geen email");
      }
      const userPayload = { email, name };
      setAuthUser(userPayload);
      sessionStorage.setItem("authUser", JSON.stringify(userPayload));
      setApiAuthEmail(email);
      setIsAuthenticated(true);
      setLoginForm({ email, password: "" });
      setAuthStatus({ ok: true, msg: "Inloggen geslaagd." });
    } catch (err) {
      setAuthStatus({ ok: false, msg: "Login mislukt. Controleer gegevens." });
    } finally {
      setAuthSubmitting(false);
    }
  };

  const handleLogout = () => {
    sessionStorage.removeItem("authUser");
    setApiAuthEmail(null);
    setAuthUser(null);
    setIsAuthenticated(false);
    setAuthStatus(null);
    setLoginForm(initialLoginForm);
    setEmployees([]);
    setSelectedId(null);
    setForm(emptyForm);
    setStatus(null);
  };

  const submitForm = async (e) => {
    e.preventDefault();
    setStatus(null);
    setSubmitting(true);

    try {
      await createEmployee(form);
      setStatus({
        ok: true,
        msg: "Medewerker aangemaakt. EC2 + IAM rol worden nu uitgerold.",
      });
      setForm(emptyForm);
      setSelectedId(null);
      await fetchEmployees();
    } catch (err) {
      setStatus({
        ok: false,
        msg: "Er ging iets mis bij het aanmaken.",
      });
    } finally {
      setSubmitting(false);
    }
  };

  const onSelectEmployee = (emp) => {
    setSelectedId(emp.employeeId);
    setForm({
      name: emp.name || "",
      email: emp.email || "",
      department: emp.department || "",
    });
    setStatus(null);
  };

  const onUpdate = async () => {
    if (!selectedId) return;
    setSubmitting(true);
    setStatus(null);
    try {
      await updateEmployee(selectedId, form);
      setStatus({ ok: true, msg: "Medewerker bijgewerkt." });
      await fetchEmployees();
    } catch (err) {
      setStatus({ ok: false, msg: "Bijwerken mislukt." });
    } finally {
      setSubmitting(false);
    }
  };

  const onDelete = async () => {
    if (!selectedId) return;
    setSubmitting(true);
    setStatus(null);
    try {
      const res = await deleteEmployee(selectedId);
      // backend now kicks off an asynchronous delete job and marks status=DELETING
      if (res?.data?.status === "DELETING") {
        setStatus({
          ok: true,
          msg: "Verwijderen gestart — resources worden opgeruimd. Dit kan een paar minuten duren.",
        });
      } else {
        setStatus({ ok: true, msg: "Medewerker verwijderd." });
      }
      setForm(emptyForm);
      setSelectedId(null);
      await fetchEmployees();
    } catch (err) {
      setStatus({ ok: false, msg: "Verwijderen mislukt." });
    } finally {
      setSubmitting(false);
    }
  };

  const onNewClick = () => {
    setSelectedId(null);
    setForm(emptyForm);
    setStatus(null);
  };

  if (!isAuthenticated) {
    return (
      <div className="login-page">
        <div className="login-card">
          <p className="eyebrow">Beveiligde toegang</p>
          <h1>CS3 Employee Portal</h1>
          <p className="muted">Log in met je HR account om verder te gaan.</p>

          <form className="form" onSubmit={handleLoginSubmit}>
            <label>
              E-mail
              <input
                type="email"
                value={loginForm.email}
                onChange={(e) =>
                  setLoginForm({ ...loginForm, email: e.target.value })
                }
                placeholder="hr@innovatech.com"
                required
              />
            </label>

            <label>
              Wachtwoord
              <input
                type="password"
                value={loginForm.password}
                onChange={(e) =>
                  setLoginForm({ ...loginForm, password: e.target.value })
                }
                placeholder="*******"
                required
              />
            </label>

            <button type="submit" className="btn-primary" disabled={authSubmitting}>
              {authSubmitting ? "Bezig..." : "Inloggen"}
            </button>
          </form>

          {authStatus && (
            <div className={`status-box ${authStatus.ok ? "success" : "error"}`}>
              {authStatus.msg}
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="page">
      <header className="hero">
        <div className="auth-bar">
          <div className="auth-user">
            <span className="muted">Ingelogd als</span>
            <strong>{authUser?.name || authUser?.email}</strong>
          </div>
          <button className="ghost" onClick={handleLogout}>
            Uitloggen
          </button>
        </div>
        <div>
          <p className="eyebrow">Cloud native onboarding</p>
          <h1>CS3 Employee Portal</h1>
          <p className="lede">
            Elke klik maakt een eigen pod, IAM rol, DynamoDB record en een
            dedicated VM. Geen gedeelde pods, geen handwerk.
          </p>
          <div className="tags">
            <span>EKS</span>
            <span>EventBridge</span>
            <span>SQS</span>
            <span>Per-user Pod</span>
          </div>
        </div>
        <div className="pillars">
          <div className="pillar">
            <p className="label">Flow</p>
            <p>
              Frontend → EKS backend → EventBridge → SQS → Job Pod → AWS (IAM,
              EC2, DynamoDB)
            </p>
          </div>
          <div className="pillar">
            <p className="label">Security</p>
            <p>IRSA, per-employee IAM role, instance profile, tags op EC2.</p>
          </div>
        </div>
      </header>

      <main className="grid">
        <section className="panel form-panel">
          <div className="panel-head">
            <div>
              <p className="eyebrow">
                {selectedId ? "Medewerker bewerken" : "Nieuwe medewerker"}
              </p>
              <h2>{selectedId ? "Wijzig gegevens" : "Provisioning"}</h2>
              <p className="muted">
                {selectedId
                  ? "Pas gegevens aan en sla op."
                  : "Maak een account aan; wij starten automatisch een pod en EC2."}
              </p>
            </div>
            <div className="actions">
              <button className="ghost" onClick={onNewClick}>
                + Medewerker toevoegen
              </button>
              <div className="badge live">Live</div>
            </div>
          </div>

          <form onSubmit={submitForm} className="form">
            <label>
              Naam
              <input
                type="text"
                placeholder="Bijv. Alex Janssen"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                required
              />
            </label>

            <label>
              E-mail
              <input
                type="email"
                placeholder="gebruiker@bedrijf.nl"
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
                required
              />
            </label>

            <label>
              Afdeling
              <input
                type="text"
                placeholder="Bijv. Security, Dev, Ops"
                value={form.department}
                onChange={(e) =>
                  setForm({ ...form, department: e.target.value })
                }
                required
              />
            </label>

            <div className="form-actions">
              <button type="submit" className="btn-primary" disabled={submitting}>
                {submitting && !selectedId ? "Bezig..." : "Opslaan"}
              </button>
              {selectedId && (
                <>
                  <button
                    type="button"
                    className="btn-secondary"
                    disabled={submitting || selectedEmployee?.status === "DELETING"}
                    onClick={onUpdate}
                  >
                    {submitting ? "Bezig..." : "Bijwerken"}
                  </button>
                  <button
                    type="button"
                    className="btn-danger"
                    disabled={submitting || selectedEmployee?.status === "DELETING"}
                    onClick={onDelete}
                  >
                    {selectedEmployee?.status === "DELETING" ? "Opkuisen..." : "Verwijderen"}
                  </button>
                </>
              )}
            </div>
          </form>

          {status && (
            <div className={`status-box ${status.ok ? "success" : "error"}`}>
              {status.msg}
            </div>
          )}
        </section>

        <section className="panel info-panel">
          <div className="panel-head">
            <p className="eyebrow">Huidige medewerkers</p>
            <h2>Records in DynamoDB</h2>
          </div>

          <div className="list">
            {loading && <div className="muted">Laden...</div>}
            {!loading && employees.length === 0 && (
              <div className="muted">Nog geen medewerkers.</div>
            )}
            {!loading &&
              employees.map((emp) => (
                <button
                  key={emp.employeeId}
                  className={`list-item ${
                    selectedId === emp.employeeId ? "active" : ""
                  }`}
                  onClick={() => onSelectEmployee(emp)}
                >
                  <div>
                    <p className="list-title">{emp.name} {emp.status === 'DELETING' && (<span className="muted">• Opkuisen</span>)}</p>
                    <p className="list-sub">
                      {emp.email} • {emp.department}
                    </p>
                  </div>
                  <div className={`pill pill-${(emp.status || "unknown").toLowerCase()}`}>
                    {emp.status || "UNKNOWN"}
                  </div>
                </button>
              ))}
          </div>

          <div className="panel-head">
            <p className="eyebrow">Architectuur</p>
            <h2>Per-user lifecycle</h2>
          </div>
          <ul className="step-list">
            <li>
              <span className="step-dot" />
              Backend in EKS schrijft event naar EventBridge/SQS.
            </li>
            <li>
              <span className="step-dot" />
              Job controller spawnt een losse pod per user (geen reuse).
            </li>
            <li>
              <span className="step-dot" />
              Worker maakt IAM rol + instance profile, start EC2, schrijft naar DynamoDB.
            </li>
            <li>
              <span className="step-dot" />
              Pod cleaned up na run (TTL), status bijgewerkt.
            </li>
          </ul>
        </section>
      </main>
    </div>
  );
}
