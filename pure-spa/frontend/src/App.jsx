import { lazy, Suspense } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import { RequireAuth, useAuth } from './auth.jsx';
import Layout from './Layout.jsx';
import Login from './pages/Login.jsx';
import { Skeleton } from './ui.jsx';

// Every section is a separate lazily-loaded chunk with a hashed filename
const page = (loader, name) => lazy(() => loader().then((m) => ({ default: m[name] })));
const Dashboard = page(() => import('./pages/Dashboard.jsx'), 'Dashboard');
const Announcement = page(() => import('./pages/Dashboard.jsx'), 'Announcement');
const LeaveList = page(() => import('./pages/Leave.jsx'), 'LeaveList');
const LeaveDetail = page(() => import('./pages/Leave.jsx'), 'LeaveDetail');
const LeaveApply = page(() => import('./pages/Leave.jsx'), 'LeaveApply');
const ClaimsList = page(() => import('./pages/Claims.jsx'), 'ClaimsList');
const ClaimNew = page(() => import('./pages/Claims.jsx'), 'ClaimNew');
const ClaimDetail = page(() => import('./pages/Claims.jsx'), 'ClaimDetail');
const Directory = page(() => import('./pages/People.jsx'), 'Directory');
const ProfileView = page(() => import('./pages/People.jsx'), 'ProfileView');
const TeamCalendar = page(() => import('./pages/People.jsx'), 'TeamCalendar');
const Profile = page(() => import('./pages/Profile.jsx'), 'Profile');
const Approvals = page(() => import('./pages/Admin.jsx'), 'Approvals');
const Users = page(() => import('./pages/Admin.jsx'), 'Users');
const UserForm = page(() => import('./pages/Admin.jsx'), 'UserForm');
const Help = page(() => import('./pages/Misc.jsx'), 'Help');
const Terms = page(() => import('./pages/Misc.jsx'), 'Terms');
const Register = page(() => import('./pages/Register.jsx'), 'Register');
const NotFound = page(() => import('./pages/Misc.jsx'), 'NotFound');
const Forbidden = page(() => import('./pages/Misc.jsx'), 'Forbidden');

const MANAGERS = ['manager', 'hr_admin'];

function Home() {
  const { user, ready } = useAuth();
  if (!ready) return null;
  return <Navigate to={user ? '/dashboard' : '/login'} replace />;
}

// Public pages: inside the app shell when signed in, standalone otherwise
function PublicPage({ children }) {
  const { user, ready } = useAuth();
  if (!ready) return null;
  if (user) return <Layout />;
  return <div className="container py-5" style={{ maxWidth: 760 }}><Suspense fallback={<Skeleton />}>{children}</Suspense></div>;
}

export default function App() {
  return (
    <Suspense fallback={<Skeleton rows={6} />}>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route path="/help" element={<PublicPage><Help /></PublicPage>}>
          <Route index element={<Help />} />
        </Route>
        <Route path="/terms" element={<PublicPage><Terms /></PublicPage>}>
          <Route index element={<Terms />} />
        </Route>
        <Route element={<RequireAuth><Layout /></RequireAuth>}>
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/announcements/:id" element={<Announcement />} />
          <Route path="/leave" element={<LeaveList />} />
          <Route path="/leave/apply" element={<LeaveApply />} />
          <Route path="/leave/:id" element={<LeaveDetail />} />
          <Route path="/claims" element={<ClaimsList />} />
          <Route path="/claims/new" element={<ClaimNew />} />
          <Route path="/claims/:id" element={<ClaimDetail />} />
          <Route path="/directory" element={<Directory />} />
          <Route path="/directory/:id" element={<ProfileView />} />
          <Route path="/calendar" element={<TeamCalendar />} />
          <Route path="/profile/:tab?" element={<Profile />} />
          <Route path="/admin/approvals" element={<RequireAuth roles={MANAGERS}><Approvals /></RequireAuth>} />
          <Route path="/admin/users" element={<RequireAuth roles={['hr_admin']}><Users /></RequireAuth>} />
          <Route path="/admin/users/new" element={<RequireAuth roles={['hr_admin']}><UserForm /></RequireAuth>} />
          <Route path="/admin/users/:id" element={<RequireAuth roles={['hr_admin']}><UserForm /></RequireAuth>} />
          <Route path="/forbidden" element={<Forbidden />} />
          {/* Soft 404: nginx answers 200 for every path; only the page content says "not found" */}
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </Suspense>
  );
}
