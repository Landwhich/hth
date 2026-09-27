import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { ChevronLeft, Calendar, Image as ImageIcon } from 'lucide-react';

export default function Profile() {
  const { id } = useParams();
  const [profile, setProfile] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedSnap, setSelectedSnap] = useState(null);

  useEffect(() => {
    const fetchProfile = async () => {
      setIsLoading(true);
      setError(null);
      try {
        const response = await fetch(`http://localhost:8000/profile/${id}`);
        if (!response.ok) {
          throw new Error('User not found');
        }
        const data = await response.json();
        setProfile(data);
      } catch (err) {
        console.error("Failed to fetch profile:", err);
        setError(err.message);
      } finally {
        setIsLoading(false);
      }
    };
    
    if (id) {
      fetchProfile();
    }
  }, [id]);

  if (isLoading) {
    return (
      <div className="flex h-full w-full items-center justify-center font-bold text-neutral-500 uppercase tracking-widest">
        Loading Profile...
      </div>
    );
  }

  if (error || !profile) {
    return (
      <div className="flex flex-col h-full w-full items-center justify-center text-white gap-4">
        <h2 className="text-2xl font-bold">User Not Found</h2>
        <Link to="/leaderboard" className="text-neutral-400 hover:text-white flex items-center gap-2">
          <ChevronLeft size={20} /> Back to Leaderboard
        </Link>
      </div>
    );
  }

  const joinDate = new Date(profile.joined_at).toLocaleDateString('en-US', {
    month: 'long',
    year: 'numeric'
  });

  return (
    <>
      <div className="flex flex-col items-center w-full min-h-full bg-neutral-950 text-white py-10 px-4 overflow-y-auto">
        <div className="w-full max-w-4xl flex flex-col gap-10">
        
        {/* Header Navigation */}
        <div className="w-full">
          <Link to="/leaderboard" className="inline-flex items-center gap-2 text-neutral-500 hover:text-white transition-colors text-sm font-semibold uppercase tracking-wider">
            <ChevronLeft size={18} /> Wall of Fame
          </Link>
        </div>

        {/* Profile Header */}
        <div className="flex flex-col md:flex-row items-center md:items-start gap-6 bg-neutral-900 p-6 rounded-2xl border border-neutral-800">
          <img 
            src={profile.avatar} 
            alt={profile.username} 
            className="w-32 h-32 rounded-full ring-4 ring-neutral-800 object-cover bg-neutral-950" 
          />
          
          <div className="flex flex-col items-center md:items-start flex-1 gap-2">
            <h1 className="text-3xl md:text-5xl font-black tracking-tight">{profile.username}</h1>
            <div className="flex items-center gap-2 text-neutral-400 font-mono text-sm">
              <Calendar size={16} /> Joined {joinDate}
            </div>
          </div>
          
          <div className="flex gap-6 mt-4 md:mt-0 bg-neutral-950 p-4 rounded-xl border border-neutral-800">
            <div className="flex flex-col items-center">
              <span className="text-3xl font-black text-white">{profile.total_snaps}</span>
              <span className="text-xs text-neutral-500 font-mono tracking-widest uppercase mt-1">Snaps</span>
            </div>
            <div className="w-px bg-neutral-800" />
            <div className="flex flex-col items-center">
              <span className={`text-3xl font-black ${profile.average_score < 50 ? 'text-red-500' : 'text-green-500'}`}>
                {profile.average_score.toFixed(1)}
              </span>
              <span className="text-xs text-neutral-500 font-mono tracking-widest uppercase mt-1">Avg Score</span>
            </div>
          </div>
        </div>

        {/* Photo Grid */}
        <div className="flex flex-col gap-6">
          <div className="flex items-center gap-3 border-b border-neutral-800 pb-4">
            <ImageIcon className="text-neutral-500" />
            <h2 className="text-xl font-bold tracking-wider uppercase">Parking History</h2>
          </div>
          
          {profile.snaps.length === 0 ? (
            <div className="text-center py-20 text-neutral-600 font-mono">
              No snaps uploaded yet.
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {profile.snaps.map((snap) => (
                  <div 
                    key={snap.id} 
                    className="flex flex-col bg-neutral-900 rounded-xl overflow-hidden border border-neutral-800 group cursor-pointer hover:ring-2 hover:ring-neutral-700 transition-all"
                    onClick={() => setSelectedSnap(snap)}
                  >
                    <div className="relative aspect-video overflow-hidden bg-black">
                      {snap.image_url ? (
                        <img 
                          src={snap.image_url} 
                          alt="Parking Snap" 
                          className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
                        />
                      ) : (
                        <div className="w-full h-full flex items-center justify-center text-neutral-700">No Image</div>
                      )}
                      <div className="absolute top-3 right-3 bg-black/80 backdrop-blur-sm px-3 py-1 rounded-full border border-white/10">
                        <span className={`font-black ${snap.score < 50 ? 'text-red-500' : 'text-green-500'}`}>
                          {snap.score.toFixed(1)}
                        </span>
                      </div>
                    </div>
                    <div className="p-4 flex justify-between items-center bg-neutral-900">
                      <span className="text-xs text-neutral-500 font-mono">
                        {new Date(snap.created_at).toLocaleDateString()}
                      </span>
                      <span className="text-xs text-neutral-600 font-mono uppercase tracking-widest">
                        Snap #{snap.id.substring(0, 6)}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

        </div>
      </div>

      {/* Full Screen Image Modal */}
      {selectedSnap && (
        <div 
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/95 backdrop-blur-md p-4 animate-in fade-in duration-200"
          onClick={() => setSelectedSnap(null)}
        >
          <div className="relative max-w-5xl w-full max-h-full flex flex-col items-center justify-center" onClick={(e) => e.stopPropagation()}>
            {/* Close button */}
            <button 
              onClick={() => setSelectedSnap(null)}
              className="absolute -top-12 right-0 md:-right-12 md:top-0 text-neutral-500 hover:text-white transition-colors bg-neutral-900 md:bg-transparent rounded-full p-2"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
            </button>
            
            {/* Image */}
            {selectedSnap.image_url && (
              <img 
                src={selectedSnap.image_url} 
                alt="Parking Snap Full" 
                className="w-full max-h-[80vh] object-contain rounded-xl border border-neutral-800 shadow-2xl"
              />
            )}
            
            {/* Overlay Info */}
            <div className="absolute bottom-4 inset-x-4 md:bottom-8 md:inset-x-auto bg-black/80 backdrop-blur-md border border-neutral-800 rounded-2xl p-4 md:px-8 md:py-6 flex flex-row items-center gap-6 shadow-2xl">
              <div className="flex flex-col">
                <span className="text-[10px] md:text-xs text-neutral-500 font-mono tracking-widest uppercase mb-1">Score</span>
                <span className={`text-4xl md:text-6xl font-black ${selectedSnap.score < 50 ? 'text-red-500' : 'text-green-500'}`}>
                  {selectedSnap.score.toFixed(1)}
                </span>
              </div>
              <div className="w-px h-12 bg-neutral-800" />
              <div className="flex flex-col">
                <span className="text-[10px] md:text-xs text-neutral-500 font-mono tracking-widest uppercase mb-1">Date Scanned</span>
                <span className="text-base md:text-xl font-bold text-white tracking-tight">
                  {new Date(selectedSnap.created_at).toLocaleDateString()}
                </span>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
