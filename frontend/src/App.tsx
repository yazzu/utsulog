import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';

// APIから返される検索結果の型定義
interface SearchResult {
  id: string;
  videoId: string;
  datetime: string;
  elapsedTime: string;
  author: string;
  message: string;
  videoTitle: string;
  thumbnailUrl: string;
}

// elapsedTime (hh:mm:ss) を秒に変換するヘルパー関数
const elapsedTimeSeconds = (elapsedTime: string): number => {
  const parts = elapsedTime.split(':').map(Number);
  let seconds = 0;
  if (parts.length === 3) {
    seconds = parts[0] * 3600 + parts[1] * 60 + parts[2];
  } else if (parts.length === 2) {
    seconds = parts[0] * 60 + parts[1];
  } else if (parts.length === 1) {
    seconds = parts[0];
  }
  return seconds;
};

// hh:mm:ss 形式に変換するヘルパー関数
const formatTimestamp = (elapsedTime: string): string => {
  return elapsedTime;
};

function App() {
  const [emojiPickerOpen, setEmojiPickerOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [from, setFrom] = useState(0);
  const [hasMore, setHasMore] = useState(true);
  const [isExactMatch, setIsExactMatch] = useState(false);

  // デバウンスされたAPIリクエスト
  const debouncedSearch = useCallback((query: string, reset: boolean = false) => {
    if (query.trim() === '') {
      setSearchResults([]);
      setFrom(0);
      setHasMore(true);
      return;
    }
    
    if (reset) {
      setSearchResults([]);
      setFrom(0);
      setHasMore(true);
    }

    setIsLoading(true);
    axios.get(`http://localhost:8000/search?q=${encodeURIComponent(query)}&from_=${reset ? 0 : from}&exact=${isExactMatch}`)
      .then(response => {
        if (response.data.length === 0) {
          setHasMore(false);
        } else {
          setSearchResults(prevResults => reset ? response.data : [...prevResults, ...response.data]);
          setFrom(prevFrom => prevFrom + response.data.length);
        }
      })
      .catch(error => {
        console.error("Error fetching search results:", error);
      })
      .finally(() => {
        setIsLoading(false);
      });
  }, [from, isExactMatch]);

  useEffect(() => {
    const handler = setTimeout(() => {
      debouncedSearch(searchQuery, true); // 新しい検索なのでリセット
    }, 300); // 300msのデバウンス

    return () => {
      clearTimeout(handler);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchQuery, isExactMatch]);

  useEffect(() => {
    const mainElement = document.querySelector('main');
    if (!mainElement) return;

    const handleScroll = () => {
      if (
        mainElement.scrollHeight - mainElement.scrollTop <= mainElement.clientHeight + 50 &&
        !isLoading &&
        hasMore
      ) {
        debouncedSearch(searchQuery, false); // 追加読み込み
      }
    };

    mainElement.addEventListener('scroll', handleScroll);
    return () => {
      mainElement.removeEventListener('scroll', handleScroll);
    };
  }, [isLoading, hasMore, searchQuery, debouncedSearch]);

  return (
    <div className="flex h-screen bg-slate-50">
      {/* Sidebar */}
      <aside className="w-72 flex-shrink-0 bg-white border-r border-slate-200 p-6 hidden lg:block overflow-y-auto">
        <h2 className="text-xl font-bold text-slate-800 mb-6">フィルター</h2>
        
        {/* Date Filter */}
        <div className="space-y-4">
          <h3 className="text-sm font-semibold text-slate-600 uppercase">動画投稿日</h3>
          <div>
            <label htmlFor="date-from" className="block text-sm font-medium text-slate-700 mb-1">From</label>
            <input type="date" id="date-from" name="date-from" className="w-full px-3 py-2 border border-slate-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm" />
          </div>
          <div>
            <label htmlFor="date-to" className="block text-sm font-medium text-slate-700 mb-1">To</label>
            <input type="date" id="date-to" name="date-to" className="w-full px-3 py-2 border border-slate-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm" />
          </div>
        </div>

        {/* Author Filter */}
        <div className="mt-8">
          <h3 className="text-sm font-semibold text-slate-600 uppercase mb-4">投稿者名</h3>
          <div className="relative">
            <input type="text" id="author-search" name="author-search" placeholder="投稿者名で検索..." className="w-full pl-10 pr-4 py-2 border border-slate-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm" />
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
              <svg className="w-4 h-4 text-slate-400" xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
            </div>
          </div>
          <div className="mt-4 space-y-2 max-h-48 overflow-y-auto">
            <label className="flex items-center space-x-2 cursor-pointer">
              <input type="checkbox" className="rounded border-slate-300 text-blue-600 focus:ring-blue-500" />
              <span className="text-sm text-slate-700">サンプルユーザー1</span>
            </label>
            <label className="flex items-center space-x-2 cursor-pointer">
              <input type="checkbox" className="rounded border-slate-300 text-blue-600 focus:ring-blue-500" />
              <span className="text-sm text-slate-700">サンプルユーザー2</span>
            </label>
            <label className="flex items-center space-x-2 cursor-pointer">
              <input type="checkbox" className="rounded border-slate-300 text-blue-600 focus:ring-blue-500" />
              <span className="text-sm text-slate-700">長めの名前のユーザーさん</span>
            </label>
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 overflow-y-auto">
        <div className="max-w-4xl mx-auto p-4 sm:p-6 lg:p-8">
          <header className="mb-8">
            <h1 className="text-3xl font-bold text-slate-900 mb-2">うつろぐ！</h1>
            <p className="text-slate-600">Utsuro CH. 氷室うつろのチャットログを検索できるよ。</p>

            {/* Search Box */}
            <div className="mt-6 relative">
              <input 
                type="text" 
                placeholder="検索キーワードを入力（例: 「お疲れ様」 😂）"
                className="w-full pl-5 pr-12 py-3 border border-slate-300 rounded-full shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-base"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
              <button 
                onClick={() => setEmojiPickerOpen(!emojiPickerOpen)}
                className="absolute inset-y-0 right-0 flex items-center justify-center w-12 h-full text-slate-500 hover:text-blue-600 rounded-full focus:outline-none"
                aria-label="絵文字ピッカーを開く"
              >
                <svg className="w-6 h-6" xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"></circle><path d="M8 14s1.5 2 4 2 4-2 4-2"></path><line x1="9" y1="9" x2="9.01" y2="9"></line><line x1="15" y1="9" x2="15.01" y2="9"></line></svg>
              </button>

              {/* Emoji Picker */}
              {emojiPickerOpen && (
                <div 
                  className="absolute top-full right-0 mt-2 w-72 bg-white border border-slate-200 rounded-lg shadow-xl z-10 p-4"
                >
                  <h4 className="text-sm font-semibold text-slate-700 mb-3">カスタム絵文字</h4>
                  <div className="grid grid-cols-6 gap-2">
                    {/* Emoji buttons... */}
                  </div>
                </div>
              )}
            </div>
            {/* Exact Match Toggle */}
            <div className="flex justify-end mt-2 mr-4">
              <label className="flex items-center space-x-2 cursor-pointer">
                <input 
                  type="checkbox" 
                  className="rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                  checked={isExactMatch}
                  onChange={(e) => setIsExactMatch(e.target.checked)}
                />
                <span className="text-sm text-slate-600">完全一致で検索</span>
              </label>
            </div>
          </header>

          {/* Search Results */}
          <section className="space-y-4">
            <h3 className="text-lg font-semibold text-slate-800">
              検索結果 ({searchResults.length}件)
            </h3>

            {searchResults.length > 0 ? (
              searchResults.map((result) => (
                <div key={result.id} className="relative group">
                  <div className="bg-white p-5 rounded-lg shadow-md border border-slate-200 hover:shadow-lg hover:border-blue-300 transition-all duration-200 ease-in-out">
                    <div className="flex items-center justify-between mb-3">
                      <div className="flex items-center space-x-3">
                        <img src={`https://placehold.co/40x40/cbd5e1/475569?text=${result.author.charAt(0)}`} alt={`${result.author} Avatar`} className="w-10 h-10 rounded-full" />
                        <div>
                          <p className="font-semibold text-slate-800">{result.author}</p>
                          <p className="text-sm text-slate-500">動画: 「{result.videoTitle}」</p>
                          <p className="text-sm text-slate-500">投稿日: {result.datetime}</p>
                        </div>
                      </div>
                      <span className="text-sm font-medium text-slate-600 bg-slate-100 px-3 py-1 rounded-full">
                        {formatTimestamp(result.elapsedTime)}
                      </span>
                    </div>
                    <p className="text-slate-700 leading-relaxed" dangerouslySetInnerHTML={{ __html: result.message.replace(new RegExp(searchQuery, "gi"), (match) => `<span class="font-bold text-blue-600">${match}</span>`) }} />
                  </div>
                  <div className="absolute left-1/2 -translate-x-1/2 bottom-full mb-3 w-64 opacity-0 invisible group-hover:opacity-100 group-hover:visible group-hover:bottom-full transition-all duration-200 ease-in-out z-20">
                    <div className="bg-black bg-opacity-90 text-white rounded-lg shadow-xl overflow-hidden">
                      <img src={result.thumbnailUrl} alt={`Video thumbnail at ${formatTimestamp(result.elapsedTime)}`} className="w-full h-auto" />
                      <div className="p-3">
                        <p className="text-sm font-semibold mb-1">{result.videoTitle}</p>
                        <a href={`https://www.youtube.com/watch?v=${result.videoId}&t=${elapsedTimeSeconds(result.elapsedTime)}s`} target="_blank" rel="noopener noreferrer" className="text-xs text-blue-300 hover:text-blue-200 underline flex items-center space-x-1">
                          <svg className="w-3 h-3" xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"></path><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"></path></svg>
                          <span>{formatTimestamp(result.elapsedTime)} から再生</span>
                        </a>
                      </div>
                    </div>
                  </div>
                </div>
              ))
            ) : (
              <div className="text-center py-12 text-slate-500">
                {isLoading ? '検索中...' : (searchQuery ? '検索結果が見つかりませんでした。' : '検索キーワードを入力してください。')}
              </div>
            )}
            {isLoading && <div className="text-center py-4">読み込み中...</div>}
            {!hasMore && searchResults.length > 0 && <div className="text-center py-4 text-slate-500">これ以上検索結果はありません。</div>}
          </section>
        </div>
      </main>
    </div>
  );
}

export default App;
