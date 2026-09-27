import './App.css';
import { createBrowserRouter, RouterProvider, Outlet, Link, NavLink } from 'react-router-dom';
import { Auth0Provider, useAuth0, withAuthenticationRequired } from '@auth0/auth0-react';
import { useEffect } from 'react';
import PhotoHandler from './components/Upload';
import Landing from './pages/Landing';
import Leaderboard from './pages/Leaderboard';
import Profile from './pages/Profile';
import { SquareParking, Trophy, LogIn, LogOut } from 'lucide-react';

// Root layout that wraps every page
function RootLayout() {
  const { isAuthenticated, loginWithRedirect, logout, user, getAccessTokenSilently } = useAuth0();

  // Sync user to backend when they successfully log in
  useEffect(() => {
    const syncUser = async () => {
      if (isAuthenticated && user) {
        try {
          const token = await getAccessTokenSilently();
          await fetch('http://localhost:8000/auth/sync', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              Authorization: `Bearer ${token}`
            },
            body: JSON.stringify({ 
              email: user.email, 
              username: user.name,
              picture: user.picture
            })
          });
        } catch (error) {
          console.error('Error syncing user:', error);
        }
      }
    };
    syncUser();
  }, [isAuthenticated, user, getAccessTokenSilently]);

  return (
    <main className="flex h-svh w-svw overflow-hidden bg-neutral-950">
      {/* Sleek Sidebar Navigation */}
      <nav className="flex flex-col items-center py-5 bg-neutral-950 border-r border-neutral-800/80 h-full w-20 shrink-0 select-none">
        {/* Brand / Home link */}
        <Link 
          to="/" 
          title="Park Better"
          className="group flex items-center justify-center w-11 h-11 rounded-xl bg-white text-black font-black text-sm tracking-tighter hover:scale-105 transition-all duration-200 shadow-md"
        >
          PB
        </Link>

        <div className="w-8 h-px bg-neutral-800 my-4" />

        {/* Main Navigation Links */}
        <div className="flex flex-col items-center gap-3 w-full px-3">
          <NavLink
            to="/app"
            title="Rate Parking"
            className={({ isActive }) =>
              `flex items-center justify-center w-11 h-11 rounded-xl transition-all duration-200 ${
                isActive
                  ? 'bg-neutral-800 text-white shadow-sm ring-1 ring-neutral-700'
                  : 'text-neutral-400 hover:text-white hover:bg-neutral-900'
              }`
            }
          >
            <SquareParking size={24} />
          </NavLink>

          <NavLink
            to="/leaderboard"
            title="Leaderboard"
            className={({ isActive }) =>
              `flex items-center justify-center w-11 h-11 rounded-xl transition-all duration-200 ${
                isActive
                  ? 'bg-neutral-800 text-white shadow-sm ring-1 ring-neutral-700'
                  : 'text-neutral-400 hover:text-white hover:bg-neutral-900'
              }`
            }
          >
            <Trophy size={22} />
          </NavLink>
        </div>

        {/* User Auth Section (Pinned cleanly at the bottom) */}
        <div className="mt-auto flex flex-col items-center gap-3 w-full px-3">
          <div className="w-8 h-px bg-neutral-800 mb-1" />

          {!isAuthenticated ? (
            <button
              onClick={() => loginWithRedirect()}
              title="Log In"
              className="group flex flex-col items-center justify-center w-11 h-11 rounded-xl text-neutral-400 hover:text-white hover:bg-neutral-900 transition-all duration-200"
            >
              <LogIn size={20} className="group-hover:scale-110 transition-transform" />
            </button>
          ) : (
            <div className="flex flex-col items-center gap-2">
              <Link to={`/profile/${encodeURIComponent(user.sub)}`} className="relative group cursor-pointer" title="My Profile">
                <img
                  src={user.picture}
                  alt={user.name}
                  className="w-10 h-10 rounded-full ring-2 ring-neutral-700 group-hover:ring-white transition-all object-cover"
                />
                <span className="absolute bottom-0 right-0 w-2.5 h-2.5 bg-emerald-500 rounded-full border-2 border-neutral-950" />
              </Link>

              <button
                onClick={() => logout({ logoutParams: { returnTo: window.location.origin } })}
                title="Log Out"
                className="flex items-center justify-center w-9 h-9 rounded-lg text-neutral-500 hover:text-red-400 hover:bg-neutral-900 transition-all duration-200"
              >
                <LogOut size={16} />
              </button>
            </div>
          )}
        </div>
      </nav>

      {/* Main Content Area */}
      <div className="flex-1 h-full overflow-y-auto bg-neutral-950 flex items-center justify-center">
        <Outlet />
      </div>
    </main>
  );
}

// Protected Route Wrapper
const ProtectedApp = withAuthenticationRequired(PhotoHandler, {
  onRedirecting: () => <div className="flex h-full w-full items-center justify-center font-bold text-white">Loading...</div>,
});

// Router configuration
const router = createBrowserRouter([
  {
    path: '/',
    element: <RootLayout />,
    children: [
      {
        path: "/app",
        element: <ProtectedApp />,
      },
      {
        path: "/leaderboard",
        element: <Leaderboard />,
      },
      {
        path: "/profile/:id",
        element: <Profile />,
      },
      { index: true, element: <Landing /> },
    ],
  },
]);

export default function App() {
  const domain = import.meta.env.VITE_AUTH0_DOMAIN;
  const clientId = import.meta.env.VITE_AUTH0_CLIENT_ID;
  const audience = import.meta.env.VITE_AUTH0_AUDIENCE;

  // Wait until environment variables are loaded
  if (!domain || !clientId) {
    return <div className="p-10 text-xl font-bold">Please add VITE_AUTH0_DOMAIN and VITE_AUTH0_CLIENT_ID to your frontend/.env file.</div>;
  }

  return (
    <Auth0Provider
      domain={domain}
      clientId={clientId}
      authorizationParams={{
        redirect_uri: window.location.origin,
        audience: audience
      }}
      cacheLocation="localstorage"
    >
      <RouterProvider router={router} />
    </Auth0Provider>
  );
}