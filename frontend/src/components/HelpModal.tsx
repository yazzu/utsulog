import React from 'react';

interface HelpModalProps {
    isOpen: boolean;
    onClose: () => void;
}

const HelpModal: React.FC<HelpModalProps> = ({ isOpen, onClose }) => {
    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black bg-opacity-50" onClick={onClose}>
            <div
                className="relative w-full max-w-2xl bg-white rounded-lg shadow-xl overflow-hidden flex flex-col max-h-[90vh]"
                onClick={(e) => e.stopPropagation()}
            >
                <div className="flex justify-between items-center p-4 border-b border-slate-200">
                    <h3 className="text-lg font-semibold text-slate-800">使い方</h3>
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
                    <ol className="list-decimal list-outside pl-5 space-y-4 text-slate-700 text-sm leading-relaxed">
                        <li>
                            <span className="font-semibold block mb-1">検索ボックスに検索したい文字列を入力すると、実況とチャットを検索できるよ。</span>
                            <ul className="list-disc list-inside pl-2 text-slate-600">
                                <li>右端の絵文字アイコンでカスタム絵文字も入力できる</li>
                            </ul>
                        </li>
                        <li>
                            <span className="font-semibold block mb-1">スイッチで検索結果を切り替えることができるよ。</span>
                            <ul className="list-disc list-inside pl-2 text-slate-600 space-y-1">
                                <li><span className="font-medium text-slate-800">うつろ</span>： うつろちゃんの実況だけ</li>
                                <li><span className="font-medium text-slate-800">チャット</span>: チャットメッセージだけ</li>
                                <li><span className="font-medium text-slate-800">すべて</span>: 実況とチャットの両方</li>
                            </ul>
                        </li>
                        <li>
                            <span className="font-semibold block mb-1">完全一致で検索</span>
                            <ul className="list-disc list-inside pl-2 text-slate-600 space-y-1">
                                <li>チェックをつけると完全一致で検索する</li>
                                <li>チェックを外すと部分一致で検索する</li>
                            </ul>
                        </li>
                        <li>
                            <span className="font-semibold block mb-1">投稿日</span>
                            <ul className="list-disc list-inside pl-2 text-slate-600 space-y-1">
                                <li><span className="font-medium text-slate-800">新しい順</span>: 投稿日が新しい順に並ぶ</li>
                                <li><span className="font-medium text-slate-800">古い順</span>: 投稿日が古い順に並ぶ</li>
                            </ul>
                        </li>
                        <li>
                            <span className="font-semibold block mb-1">投稿日フィルター</span>
                            <ul className="list-disc list-inside pl-2 text-slate-600">
                                <li>投稿日がFromとToの間にあるもののみ表示する</li>
                            </ul>
                        </li>
                        <li>
                            <span className="font-semibold block mb-1">投稿者名</span>
                            <ul className="list-disc list-inside pl-2 text-slate-600 space-y-1">
                                <li>投稿者名が一致するもののみ表示する</li>
                                <li>ユーザ名とハンドル名のどちらでも検索できる</li>
                            </ul>
                        </li>
                        <li>
                            <span className="font-semibold block mb-1">動画で絞り込み</span>
                            <ul className="list-disc list-inside pl-2 text-slate-600">
                                <li>動画を選択して絞り込む</li>
                            </ul>
                        </li>
                    </ol>
                </div>
            </div>
        </div>
    );
};

export default HelpModal;
