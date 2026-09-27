export default function Landing() {
    return (
        <main className="flex flex-col justify-center items-center w-full min-h-screen text-white bg-neutral-950">
            <div className="flex flex-col justify-center items-center mb-16 text-center px-4">
                <h1 className="text-5xl md:text-8xl font-inter font-black uppercase tracking-tight text-white mb-4">
                    PARK BETTER
                </h1>
                <p className="font-inter text-lg md:text-xl text-neutral-400 font-light">
                    The best remedy for bad habits is public shaming
                </p>
            </div>

            <div className="flex flex-col sm:flex-row gap-3 w-full max-w-md px-6">
                <a className="w-full group" href="/app">
                    <button className="w-full relative px-6 py-3 bg-white text-black font-inter font-bold text-sm uppercase tracking-wide hover:scale-[1.02] active:scale-[0.98] transition-transform duration-200">
                        Get Started
                    </button>
                </a>
                
                <a className="w-full group" href="/leaderboard">
                    <button className="w-full relative px-6 py-3 bg-transparent border-2 border-white/20 text-white font-inter font-bold text-sm uppercase tracking-wide hover:border-white hover:bg-white/5 active:scale-[0.98] transition-all duration-200">
                        Leaderboard
                    </button>
                </a>
            </div>
        </main>
    )
}