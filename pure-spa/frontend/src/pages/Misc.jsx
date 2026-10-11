import { Link } from 'react-router-dom';
import { useAuth } from '../auth.jsx';
import { useTitle } from '../ui.jsx';

const FAQ = [
  ['leave', 'How do I apply for leave?', 'Go to Leave → Apply for leave and follow the three steps. Your manager is notified when you submit.'],
  ['claims', 'Do I need a receipt?', 'Receipts (PDF, PNG or JPG, max 5 MB) are required for claims above $25.'],
  ['password', 'I forgot my password', 'Contact HR at hr@gowork.example and they will reset it for you.'],
  ['approvals', 'Who approves my requests?', 'Your reporting manager. HR admins can approve requests for anyone.'],
  ['privacy', 'Privacy notice', 'GoWork stores only the data needed to run HR processes. Directory profiles are visible to all employees.'],
];

export function Help() {
  useTitle('Help centre');
  const { user } = useAuth();
  return (
    <>
      {!user && <Link className="d-inline-flex align-items-center gap-2 fw-bold fs-5 text-dark text-decoration-none mb-4" to="/login"><span className="gw-logo">G</span> GoWork</Link>}
      <div className="gw-page-head"><div><h1>Help centre</h1><p>Answers to the most common questions about GoWork.</p></div></div>
      <div className="gw-card">
        {FAQ.map(([id, q, a]) => (
          <div className="gw-card-body border-bottom" id={id} key={id}>
            <h2 className="h6 fw-semibold">{q}</h2>
            <p className="mb-0 text-muted">{a}</p>
          </div>
        ))}
      </div>
      {!user && <p className="mt-3"><Link to="/login">← Back to sign in</Link></p>}
    </>
  );
}

const TERMS = [
  ['use', 'Using GoWork', 'GoWork is provided to employees of GoWork Pte Ltd for managing leave, expense claims and colleague information. Use it only for work purposes and keep your password private.'],
  ['accounts', 'Your account', 'Accounts need a valid employee ID / invite code from HR. New self-registered accounts are created with the Employee role; HR can change roles and deactivate accounts at any time.'],
  ['data', 'What we store', 'Your profile details, leave requests, expense claims and uploaded receipts. Directory profiles (name, title, department, contact details) are visible to all employees.'],
  ['retention', 'How long we keep it', 'Records are kept for as long as you are employed and for seven years afterwards, as required by law.'],
  ['contact', 'Questions', 'Contact HR at hr@gowork.example for any questions about your data.'],
];

export function Terms() {
  useTitle('Terms & Privacy');
  const { user } = useAuth();
  return (
    <>
      {!user && <Link className="d-inline-flex align-items-center gap-2 fw-bold fs-5 text-dark text-decoration-none mb-4" to="/login"><span className="gw-logo">G</span> GoWork</Link>}
      <div className="gw-page-head"><div><h1>Terms & Privacy notice</h1><p>Last updated 1 January 2026</p></div></div>
      <div className="gw-card">
        {TERMS.map(([id, heading, text]) => (
          <div className="gw-card-body border-bottom" id={id} key={id}>
            <h2 className="h6 fw-semibold">{heading}</h2>
            <p className="mb-0 text-muted">{text}</p>
          </div>
        ))}
      </div>
      {!user && <p className="mt-3"><Link to="/register">← Back to create account</Link> · <Link to="/login">Sign in</Link></p>}
    </>
  );
}

function ErrorCard({ code, title, message }) {
  useTitle(title);
  return (
    <div className="gw-card gw-card-body text-center py-5">
      <div className="display-5 fw-bold text-brand">{code}</div>
      <h1 className="h4 mt-2">{title}</h1>
      <p className="text-muted">{message}</p>
      <Link className="btn btn-primary" to="/dashboard">Back to dashboard</Link>
    </div>
  );
}

export const NotFound = () => <ErrorCard code={404} title="Page not found" message="We couldn't find the page you were looking for." />;
export const Forbidden = () => <ErrorCard code={403} title="Access denied" message="You don't have access to this page." />;
