import React from 'react';

interface InquiryModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const InquiryModal: React.FC<InquiryModalProps> = ({ isOpen, onClose }) => {
  if (!isOpen) return null;

  // TODO: Replace with actual Google Form URL provided by the user
  const googleFormUrl = "https://docs.google.com/forms/d/e/1FAIpQLSf1tM-O9_9xMUS3eD2m7EuG-8adJ7TpxdaD5IpzSUnomb_jnQ/viewform?usp=header?embedded=true";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black bg-opacity-50" onClick={onClose}>
      <div
        className="relative w-full max-w-3xl h-[80vh] bg-white rounded-lg shadow-xl overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex justify-between items-center p-4 border-b border-slate-200">
          <h3 className="text-lg font-semibold text-slate-800">お問い合わせ</h3>
          <button
            onClick={onClose}
            className="text-slate-500 hover:text-slate-700 transition-colors"
            aria-label="閉じる"
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="flex-1 w-full bg-slate-50">
          <iframe
            src={googleFormUrl}
            width="100%"
            height="100%"
            frameBorder="0"
            marginHeight={0}
            marginWidth={0}
            title="Inquiry Form"
            className="w-full h-full"
          >
            読み込んでいます…
          </iframe>
        </div>
      </div>
    </div>
  );
};

export default InquiryModal;
