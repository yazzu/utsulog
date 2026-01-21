import React from 'react';

interface CautionModalProps {
    isOpen: boolean;
    onClose: () => void;
}

const CautionModal: React.FC<CautionModalProps> = ({ isOpen, onClose }) => {
    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black bg-opacity-50" onClick={onClose}>
            <div
                className="relative w-full max-w-lg bg-white rounded-lg shadow-xl overflow-hidden flex flex-col"
                onClick={(e) => e.stopPropagation()}
            >
                <div className="flex justify-between items-center p-4 border-b border-slate-200">
                    <h3 className="text-lg font-semibold text-slate-800">うつログからのおねがい</h3>
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

                <div className="p-6 overflow-y-auto">
                    <ol className="list-decimal list-outside pl-4 space-y-3 text-slate-700 text-sm leading-relaxed">
                        <li>
                            検索結果は機械学習で生成しているため、不正確な場合があります。
                            動画の内容を確認することをつよく推奨します。
                        </li>
                        <li>
                            歌枠は歌詞の著作権があるため、検索結果には含まれません。
                        </li>
                        <li>
                            氷室うつろCH.アーカイブの非公開に合わせて、検索結果が非公開となる場合があります。その場合、反映が遅くなる場合があります。
                        </li>
                        <li>
                            一部フルボイスのゲームの音声が文字起こしされてしまっています。（鋭意修正中。今しばらくお待ちください🙇‍♂️）
                        </li>
                        <li>
                            アプリや検索結果について何かご意見やご要望があれば、メニューの「お問い合わせ」からお願いします。
                        </li>
                    </ol>
                </div>
            </div>
        </div>
    );
};

export default CautionModal;
