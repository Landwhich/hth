import React, { useState, useRef, useCallback, useEffect } from 'react';
import { useDropzone } from 'react-dropzone';
import Webcam from 'react-webcam';
import { useAuth0 } from '@auth0/auth0-react';
import { RefreshCcw, Camera, UploadCloud, RotateCcw, Check } from 'lucide-react';

function dataURLtoFile(dataurl, filename) {
  const arr = dataurl.split(',');
  const mime = arr[0].match(/:(.*?);/)[1];
  const bstr = atob(arr[1]);
  let n = bstr.length;
  const u8arr = new Uint8Array(n);
  while (n--) {
    u8arr[n] = bstr.charCodeAt(n);
  }
  return new File([u8arr], filename, { type: mime });
}

const getCattyMessage = (score) => {
  const pick = (arr) => arr[Math.floor(Math.random() * arr.length)];

  if (score <= 10) return pick([
    "GET OFF THE ROADS. IMMEDIATELY.",
    "Sir, this is a parking spot, not a modern art installation.",
    "Your car has been reported to the UN.",
    "Congratulations, you've made every driving instructor cry.",
    "We've contacted your insurance. They said goodbye.",
  ]);
  if (score <= 25) return pick([
    "At least we know you're from Ottawa.",
    "You park like you learned from a fever dream.",
    "Bold choice. Wrong choice, but bold.",
    "The cone didn't deserve this.",
    "Even your GPS is embarrassed.",
  ]);
  if (score <= 40) return pick([
    "Somewhere between illegal and impressive.",
    "Technically inside the lines. We think.",
    "Your tires are… trying.",
    "This is giving 'I'll only be a minute' energy.",
    "We've seen worse. Once.",
  ]);
  if (score <= 55) return pick([
    "You're not the problem. You're just... not the solution.",
    "The bar was low and you cleared it. Barely.",
    "Average is a compliment here.",
    "Solid C+ parking. Solid. C+.",
    "Your parents would be cautiously proud.",
  ]);
  if (score <= 70) return pick([
    "Actually not bad! Call your mom.",
    "We were pleasantly surprised. Don't ruin it.",
    "Your parallel park game is improving. Slowly.",
    "Respectable. Genuinely respectable.",
    "You've earned the right to judge others.",
  ]);
  if (score <= 85) return pick([
    "Crispy lines. We respect it.",
    "Someone definitely practiced this.",
    "Top tier citizen behavior.",
    "You can park next to me any time.",
    "Ottawa wishes it had your skills.",
  ]);
  return pick([
    "PERFECT PARK. Are you even real?",
    "The engineers who painted those lines are weeping tears of joy.",
    "Mathematically flawless. We checked.",
    "You've unlocked a secret achievement: Human Being.",
    "Frame this. Literally. Frame this.",
  ]);
};

const getScoreColor = (score) => {
  if (score <= 25) return 'text-red-500';
  if (score <= 50) return 'text-orange-400';
  if (score <= 70) return 'text-yellow-400';
  if (score <= 85) return 'text-lime-400';
  return 'text-green-400';
};

export default function PhotoHandler() {
  const { getAccessTokenSilently } = useAuth0();
  const [file, setFile] = useState(null);
  const [previewUrl, setPreviewUrl] = useState(null);
  const [isCameraOpen, setIsCameraOpen] = useState(false);
  const [facingMode, setFacingMode] = useState('environment');
  const [uploadResult, setUploadResult] = useState(null);

  const webcamRef = useRef(null);

  useEffect(() => {
    if (!file) {
      setPreviewUrl(null);
      return;
    }
    const objectUrl = URL.createObjectURL(file);
    setPreviewUrl(objectUrl);
    return () => URL.revokeObjectURL(objectUrl);
  }, [file]);

  const onDrop = useCallback((acceptedFiles) => {
    if (acceptedFiles?.length > 0) {
      setFile(acceptedFiles[0]);
      setIsCameraOpen(false);
      setUploadResult(null);
    }
  }, []);

  const { getRootProps, getInputProps, isDragActive, isDragReject } = useDropzone({
    onDrop,
    accept: {
      'image/png': ['.png'],
      'image/jpeg': ['.jpg', '.jpeg'],
      'image/webp': ['.webp'],
    },
    maxFiles: 1,
    multiple: false,
    maxSize: 25 * 1024 * 1024,
  });

  const capturePhoto = useCallback(() => {
    if (!webcamRef.current) return;
    const imageSrc = webcamRef.current.getScreenshot();
    if (imageSrc) {
      const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
      const capturedFile = dataURLtoFile(imageSrc, `camera-${timestamp}.jpeg`);
      setFile(capturedFile);
      setIsCameraOpen(false);
      setUploadResult(null);
    }
  }, []);

  const toggleCamera = () => {
    setFacingMode((prev) => (prev === 'user' ? 'environment' : 'user'));
  };

  const resetAll = () => {
    setFile(null);
    setIsCameraOpen(false);
    setUploadResult(null);
  };

  const uploadFile = async () => {
    if (!file) return;
    setUploadResult({ loading: true });
    const formData = new FormData();
    formData.append('file', file);

    try {
      const token = await getAccessTokenSilently();
      const response = await fetch('http://localhost:8000/upload', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Upload failed');
      }

      const data = await response.json();
      setUploadResult({
        loading: false,
        score: data.score,
        average_score: data.average_score,
        previous_average_score: data.previous_average_score,
        message: getCattyMessage(data.score),
      });
    } catch (error) {
      console.error('Error uploading:', error);
      setUploadResult({ loading: false, error: error.message });
    }
  };

  return (
    <div className="flex flex-col items-center justify-center w-full max-w-lg mx-auto p-4">
      {previewUrl ? (
        <div className="flex flex-col items-center w-full gap-4">
          {/* Image Preview */}
          <div className="w-full flex items-center justify-center bg-black/60 rounded-xl overflow-hidden shadow-lg p-1">
            <img
              src={previewUrl}
              alt="Snapshot preview"
              className="w-full h-auto max-h-[60vh] object-contain rounded-lg"
            />
          </div>

          {/* Loading State */}
          {uploadResult?.loading && (
            <div className="w-full bg-neutral-900 border border-neutral-800 rounded-2xl p-5 text-center">
              <p className="text-neutral-400 font-mono text-sm tracking-widest uppercase animate-pulse">
                Analyzing your park...
              </p>
            </div>
          )}

          {/* Result Card */}
          {uploadResult && !uploadResult.loading && !uploadResult.error && (() => {
            const prev = uploadResult.previous_average_score;
            const curr = uploadResult.average_score;
            const delta = (prev != null && curr != null) ? (curr - prev) : null;
            const deltaSign = delta > 0 ? '+' : '';
            const deltaColor = delta > 0 ? 'text-green-400' : delta < 0 ? 'text-red-400' : 'text-neutral-400';
            const deltaArrow = delta > 0 ? '▲' : delta < 0 ? '▼' : '—';
            return (
              <div className="w-full bg-neutral-900 border border-neutral-800 rounded-2xl overflow-hidden">
                <div className="p-5 flex items-center gap-5 border-b border-neutral-800">
                  <span className={`text-5xl font-black tabular-nums ${getScoreColor(uploadResult.score)}`}>
                    {uploadResult.score.toFixed(1)}
                  </span>
                  <div className="flex flex-col gap-1">
                    <span className="text-sm text-neutral-400 font-mono tracking-widest uppercase font-bold">Your Score</span>
                    <span className="text-sm text-neutral-400 font-mono">
                      avg now: <span className="text-white font-bold">{uploadResult.average_score.toFixed(1)}</span>
                    </span>
                    {delta !== null && (
                      <span className={`text-sm font-mono font-bold ${deltaColor}`}>
                        {deltaArrow} {deltaSign}{delta.toFixed(1)} pts from last avg
                      </span>
                    )}
                  </div>
                </div>
                <div className="px-5 py-4">
                  <p className="text-white font-bold text-base md:text-lg leading-snug tracking-tight">
                    "{uploadResult.message}"
                  </p>
                </div>
              </div>
            );
          })()}

          {/* Error State */}
          {uploadResult?.error && (
            <div className="w-full bg-red-950/50 border border-red-800 rounded-2xl p-5">
              <p className="text-red-400 font-bold text-sm">Error: {uploadResult.error}</p>
            </div>
          )}

          {/* Action Buttons */}
          <div className="flex items-center gap-3 w-full">
            <button
              type="button"
              onClick={resetAll}
              className="flex-1 flex items-center justify-center gap-2 py-3 px-4 bg-neutral-800 hover:bg-neutral-700 text-white font-medium rounded-xl transition"
            >
              <RotateCcw className="w-4 h-4" />
              Retake / Replace
            </button>
            {!uploadResult && (
              <button
                type="button"
                onClick={uploadFile}
                className="flex-1 flex items-center justify-center gap-2 py-3 px-4 bg-white text-black font-bold rounded-xl transition hover:bg-neutral-200 active:scale-95"
              >
                <Check className="w-4 h-4" />
                Confirm &amp; Upload
              </button>
            )}
          </div>
        </div>
      ) : isCameraOpen ? (
        <div className="relative flex flex-col items-center w-full bg-black rounded-xl overflow-hidden shadow-lg">
          <Webcam
            ref={webcamRef}
            audio={false}
            screenshotFormat="image/jpeg"
            videoConstraints={{ facingMode }}
            className="w-full h-auto object-contain"
          />
          <div className="absolute bottom-4 flex items-center justify-around w-full px-8">
            <button
              type="button"
              onClick={toggleCamera}
              className="p-3 bg-black/50 text-white hover:bg-black/70 rounded-full transition"
              title="Flip camera"
            >
              <RefreshCcw className="w-5 h-5" />
            </button>

            <button
              type="button"
              onClick={capturePhoto}
              className="h-16 w-16 rounded-full bg-white border-4 border-gray-300 hover:border-neutral-500 shadow-md transition active:scale-90"
              title="Take photo"
            />

            <button
              type="button"
              onClick={() => setIsCameraOpen(false)}
              className="text-xs text-white bg-black/50 hover:bg-black/70 py-2 px-3 rounded-full transition"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <div className="w-full flex flex-col gap-4">
          <div
            {...getRootProps()}
            style={{
              borderColor: isDragReject ? '#ef4444' : isDragActive ? '#fff' : '#404040',
            }}
            className="border-2 border-dashed rounded-xl p-10 text-center cursor-pointer transition bg-neutral-900/40 hover:bg-neutral-800/50 text-neutral-200"
          >
            <input {...getInputProps()} />
            <UploadCloud className="w-12 h-12 mx-auto mb-3 text-neutral-500" />
            {isDragReject ? (
              <p className="text-red-400 font-bold">Please choose a single valid image</p>
            ) : isDragActive ? (
              <p className="text-white font-bold">Drop it right here.</p>
            ) : (
              <p className="font-bold text-neutral-300">Drag &amp; drop your parking snap, or click to browse</p>
            )}
            <span className="text-xs text-neutral-500 block mt-1">PNG, JPEG, or WEBP — up to 25MB</span>
          </div>

          <div className="flex items-center gap-3">
            <div className="flex-1 h-px bg-neutral-800" />
            <span className="text-xs text-neutral-600 uppercase font-mono">or</span>
            <div className="flex-1 h-px bg-neutral-800" />
          </div>

          <button
            type="button"
            onClick={() => setIsCameraOpen(true)}
            className="flex items-center justify-center gap-2 w-full py-3 px-4 bg-neutral-900 hover:bg-neutral-800 text-white font-bold rounded-xl border border-neutral-700 transition shadow-sm"
          >
            <Camera className="w-5 h-5" />
            Take Photo with Camera
          </button>
        </div>
      )}
    </div>
  );
}