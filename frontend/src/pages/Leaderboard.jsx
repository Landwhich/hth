import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Trophy, Medal, Award, Skull, AlertTriangle, Frown } from 'lucide-react';

const MOCK_LEADERBOARD = [
  { id: '1', username: 'MathewGut', average_score: 98.5, total_snaps: 14, avatar: 'https://api.dicebear.com/7.x/avataaars/svg?seed=Mathew' },
  { id: '2', username: 'ParkingPolice', average_score: 92.1, total_snaps: 42, avatar: 'https://api.dicebear.com/7.x/avataaars/svg?seed=Police' },
  { id: '3', username: 'LineCrosser99', average_score: 45.3, total_snaps: 8, avatar: 'https://api.dicebear.com/7.x/avataaars/svg?seed=Line' },
  { id: '4', username: 'ParallelPro', average_score: 88.9, total_snaps: 11, avatar: 'https://api.dicebear.com/7.x/avataaars/svg?seed=Pro' },
  { id: '5', username: 'CurbHitter', average_score: 12.4, total_snaps: 23, avatar: 'https://api.dicebear.com/7.x/avataaars/svg?seed=Curb' },
];

export default function Leaderboard() {
  const [leaders, setLeaders] = useState(MOCK_LEADERBOARD);
  const [isLoading, setIsLoading] = useState(false);
  const [mode, setMode] = useState('best'); // 'best' or 'worst'

  // Fetch live leaderboard data from backend
  useEffect(() => {
    const fetchLeaderboard = async () => {
      setIsLoading(true);
      try {
        const response = await fetch('http://localhost:8000/leaderboard');
        if (response.ok) {
          const data = await response.json();
          if (Array.isArray(data) && data.length > 0) {
            setLeaders(data);
          }
        }
      } catch (error) {
        console.error("Failed to fetch leaderboard:", error);
      } finally {
        setIsLoading(false);
      }
    };
    fetchLeaderboard();
  }, []);

  // Sort based on current mode
  const sortedLeaders = [...leaders].sort((a, b) => {
    return mode === 'best' 
      ? b.average_score - a.average_score 
      : a.average_score - b.average_score;
  });

  // Calculate color on a gradient from red (0) to green (120)
  const getScoreColor = (score) => {
    const hue = (score / 100) * 120;
    return `hsl(${hue}, 100%, 50%)`;
  };

  return (
    <div className="flex flex-col items-center w-full min-h-full bg-neutral-950 text-white py-10 px-4 overflow-y-auto">
      <div className="w-full max-w-2xl flex flex-col gap-6">
        
        <div className="flex flex-col items-center text-center gap-1 mb-2">
          <h1 className="text-3xl md:text-4xl font-black uppercase tracking-tight">Wall of Fame</h1>
          <p className="text-neutral-400 font-light text-sm md:text-base">Top Parker Ratings & Public Shaming</p>
        </div>

        {/* Mode Toggle */}
        <div className="flex items-center justify-center bg-neutral-900 rounded-lg p-1 mx-auto w-full max-w-sm">
          <button 
            onClick={() => setMode('best')}
            className={`flex-1 py-2 text-sm font-bold uppercase tracking-wider rounded-md transition-all duration-200 ${mode === 'best' ? 'bg-white text-black shadow-sm' : 'text-neutral-500 hover:text-white'}`}
          >
            Best Parkers
          </button>
          <button 
            onClick={() => setMode('worst')}
            className={`flex-1 py-2 text-sm font-bold uppercase tracking-wider rounded-md transition-all duration-200 ${mode === 'worst' ? 'bg-red-500 text-white shadow-sm' : 'text-neutral-500 hover:text-white'}`}
          >
            Worst Offenders
          </button>
        </div>

        {isLoading ? (
          <div className="flex justify-center py-10 text-neutral-500 font-bold text-sm uppercase tracking-widest">
            Loading...
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            {sortedLeaders.map((user, index) => {
              const isTop3 = index < 3;
              return (
                <div 
                  key={user.id} 
                  className={`flex items-center justify-between p-3 md:p-4 bg-neutral-900 border ${isTop3 ? 'border-white/10' : 'border-transparent'} hover:bg-neutral-800 transition-colors duration-200`}
                >
                  <div className="flex items-center gap-3 md:gap-4">
                    <div className="flex items-center justify-center w-6 md:w-8">
                      {mode === 'best' ? (
                        <>
                          {index === 0 && <Trophy className="text-yellow-400 w-5 h-5 md:w-6 md:h-6" />}
                          {index === 1 && <Medal className="text-gray-400 w-5 h-5" />}
                          {index === 2 && <Award className="text-amber-600 w-5 h-5" />}
                          {index > 2 && <span className="text-lg font-black text-neutral-600">#{index + 1}</span>}
                        </>
                      ) : (
                        <>
                          {index === 0 && <Skull className="text-red-500 w-5 h-5 md:w-6 md:h-6" />}
                          {index === 1 && <AlertTriangle className="text-orange-500 w-5 h-5" />}
                          {index === 2 && <Frown className="text-yellow-500 w-5 h-5" />}
                          {index > 2 && <span className="text-lg font-black text-neutral-600">#{index + 1}</span>}
                        </>
                      )}
                    </div>
                    
                    <Link to={`/profile/${encodeURIComponent(user.id)}`} className="hover:opacity-80 transition-opacity">
                      <img src={user.avatar} alt={user.username} className="w-8 h-8 md:w-10 md:h-10 rounded-full bg-neutral-800 object-cover" />
                    </Link>
                    
                    <div className="flex flex-col">
                      <Link to={`/profile/${encodeURIComponent(user.id)}`} className="text-base md:text-lg font-bold tracking-wide hover:underline text-white">
                        {user.username}
                      </Link>
                      <span className="text-[10px] md:text-xs text-neutral-500 font-mono tracking-wider">{user.total_snaps} SNAPS</span>
                    </div>
                  </div>

                  <div className="flex flex-col items-end">
                    <span 
                      className="text-2xl md:text-3xl font-black leading-none"
                      style={{ color: getScoreColor(user.average_score) }}
                    >
                      {user.average_score.toFixed(1)}
                    </span>
                    <span className="text-[10px] text-neutral-500 font-mono tracking-widest uppercase mt-1">AVG SCORE</span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
