import React from 'react';

interface Video {
  videoId: string;
  title: string;
  thumbnail_url: string;
}

interface VideoFilterProps {
  videos: Video[];
  selectedVideoId: string | null;
  setSelectedVideoId: (id: string | null) => void;
  onClose: () => void;
  isOpen: boolean;
}

const VideoFilter: React.FC<VideoFilterProps> = ({ videos, selectedVideoId, setSelectedVideoId, onClose, isOpen }) => {
  if (!isOpen) {
    return null;
  }

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 z-40 flex justify-center items-center" onClick={onClose}>
      <div className="bg-white rounded-lg shadow-xl w-full max-w-3xl max-h-[80vh] overflow-y-auto p-6 m-4" onClick={(e) => e.stopPropagation()}>
        <div className="flex justify-between items-center mb-4">
          <h3 className="text-lg font-semibold text-slate-800">動画で絞り込み</h3>
          <button onClick={onClose} className="text-slate-500 hover:text-slate-700">
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12"></path></svg>
          </button>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
          {videos.map((video) => (
            <div key={video.videoId}>
              <button
                onClick={() => {
                  setSelectedVideoId(video.videoId === selectedVideoId ? null : video.videoId);
                  onClose();
                }}
                className={`relative rounded-md overflow-hidden focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 w-full ${
                  selectedVideoId === video.videoId ? 'ring-2 ring-blue-500' : ''
                }`}
              >
                <img src={video.thumbnail_url} alt={video.title} className="w-full h-auto object-cover transition-transform duration-200 hover:scale-105" />
                {selectedVideoId === video.videoId && (
                  <div className="absolute inset-0 bg-blue-500 bg-opacity-50 flex items-center justify-center">
                    <svg className="w-8 h-8 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                  </div>
                )}
              </button>
              <p className="text-xs text-slate-600 mt-2 text-center">{video.title}</p>
            </div>
          ))}
        </div>
        {selectedVideoId && (
          <div className="mt-6 text-center">
            <button
              onClick={() => {
                setSelectedVideoId(null);
                onClose();
              }}
              className="text-sm text-slate-600 hover:text-blue-600"
            >
              選択を解除
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

export default VideoFilter;
