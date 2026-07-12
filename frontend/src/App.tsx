import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import VideoFilter from './components/VideoFilter';
import InquiryModal from './components/InquiryModal';
import CautionModal from './components/CautionModal';
import HelpModal from './components/HelpModal';
import { combineDateTime } from './lib/datetimeRange';

// APIのベースURLを環境変数から取得
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

// APIから返される動画の型定義
interface Video {
  videoId: string;
  title: string;
  thumbnail_url: string;
  actualStartTime: string;
}

// APIから返される検索結果の型定義
interface SearchResult {
  id: string;
  videoId: string;
  datetime: string;
  timestampSec: number;
  elapsedTime: string;
  author: string;
  message: string;
  videoTitle: string;
  thumbnailUrl: string;
  authorChannelId: string;
  authorIconUrl: string;
  type?: string;
}

// 「前後5分を表示」実行前の検索条件を保持するためのスナップショット
interface SearchFiltersSnapshot {
  searchQuery: string;
  dateFrom: string;
  timeFrom: string;
  dateTo: string;
  timeTo: string;
  authorName: string;
  selectedVideoId: string | null;
  messageType: 'all' | 'chat' | 'transcript';
  sortOrder: 'asc' | 'desc';
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

// timestamp (ms) を yyyy-mm-dd HH:MM:SS 形式に変換するヘルパー関数
const formatDate = (timestamp: number): string => {
  const date = new Date(timestamp);
  const yyyy = date.getFullYear();
  const mm = String(date.getMonth() + 1).padStart(2, '0');
  const dd = String(date.getDate()).padStart(2, '0');
  const HH = String(date.getHours()).padStart(2, '0');
  const MM = String(date.getMinutes()).padStart(2, '0');
  const SS = String(date.getSeconds()).padStart(2, '0');
  return `${yyyy}-${mm}-${dd} ${HH}:${MM}:${SS}`;
};

// timestamp (ms) を date input用の yyyy-mm-dd 形式に変換するヘルパー関数
const formatDateInputValue = (timestamp: number): string => {
  const date = new Date(timestamp);
  const yyyy = date.getFullYear();
  const mm = String(date.getMonth() + 1).padStart(2, '0');
  const dd = String(date.getDate()).padStart(2, '0');
  return `${yyyy}-${mm}-${dd}`;
};

// timestamp (ms) を time input用の HH:MM 形式に変換するヘルパー関数
const formatTimeInputValue = (timestamp: number): string => {
  const date = new Date(timestamp);
  const HH = String(date.getHours()).padStart(2, '0');
  const MM = String(date.getMinutes()).padStart(2, '0');
  return `${HH}:${MM}`;
};

// date input(yyyy-mm-dd)とtime input(HH:MM)を「MM/DD HH:MM」表示用にまとめるヘルパー関数
const formatRangeLabel = (date: string, time: string): string => {
  if (!date) return '';
  const [, month, day] = date.split('-');
  return time ? `${month}/${day} ${time}` : `${month}/${day}`;
};

// Vite specific: Import all custom emojis from the public directory
const emojiModules = import.meta.glob('/public/custom_emojis/*.png', { eager: true });
const emojiFileNames = Object.keys(emojiModules).map(path => decodeURIComponent(path.split('/').pop() || ''));

function App() {
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [emojiPickerOpen, setEmojiPickerOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [from, setFrom] = useState(0);
  const [hasMore, setHasMore] = useState(true);
  const [isExactMatch, setIsExactMatch] = useState(false);
  const [totalResults, setTotalResults] = useState(0);
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [timeFrom, setTimeFrom] = useState('');
  const [timeTo, setTimeTo] = useState('');
  const [authorName, setAuthorName] = useState('');
  const [customEmojis, setCustomEmojis] = useState<string[]>([]);
  const [emojiMap, setEmojiMap] = useState<Record<string, string>>({});
  const [videos, setVideos] = useState<Video[]>([]);
  const [selectedVideoId, setSelectedVideoId] = useState<string | null>(null);
  const [isVideoFilterOpen, setIsVideoFilterOpen] = useState(false);
  const [isInquiryOpen, setIsInquiryOpen] = useState(false);
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');
  const [messageType, setMessageType] = useState<'all' | 'chat' | 'transcript'>('all');
  const [isCautionOpen, setIsCautionOpen] = useState(false);
  const [isHelpOpen, setIsHelpOpen] = useState(false);
  const hasActiveDateRange = Boolean(dateFrom && dateTo);
  const [filterSnapshot, setFilterSnapshot] = useState<SearchFiltersSnapshot | null>(null);

  useEffect(() => {
    setCustomEmojis(emojiFileNames);

    // Fetch custom emoji mapping
    axios.get('/emojis.json')
      .then(response => {
        setEmojiMap(response.data);
      })
      .catch(error => {
        console.error("Error fetching emojis:", error);
      });

    // Check if user has seen caution modal
    const hasSeenCaution = localStorage.getItem('hasSeenCaution');
    if (!hasSeenCaution) {
      setIsCautionOpen(true);
      localStorage.setItem('hasSeenCaution', 'true');
    }
  }, []);

  // Format message with emojis and highlighting
  const formatMessage = useCallback((message: string, query: string) => {
    if (!message) return '';

    // Split by potential emoji shortcodes
    const parts = message.split(/(:[^:\s]+:)/g);

    return parts.map(part => {
      // Check if it's a known emoji
      if (emojiMap[part]) {
        return `<img src="${emojiMap[part]}" alt="${part}" class="w-5 h-5 inline-block align-text-bottom mx-0.5" />`;
      }

      // Text part: highlight query if present
      if (query) {
        return part.replace(new RegExp(query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), "gi"), (match) => `<span class="font-bold text-blue-600">${match}</span>`);
      }
      return part;
    }).join('');
  }, [emojiMap]);

  // 動画一覧を取得
  useEffect(() => {
    axios.get(`${API_BASE_URL}/videos`)
      .then(response => {
        setVideos(response.data.videos);
      })
      .catch(error => {
        console.error("Error fetching videos:", error);
      });
  }, []);

  // デバウンスされたAPIリクエスト
  const debouncedSearch = useCallback((query: string, reset: boolean = false) => {
    if (query.trim() === '' && authorName.trim() === '' && !selectedVideoId && !hasActiveDateRange) {
      setSearchResults([]);
      setFrom(0);
      setHasMore(true);
      setTotalResults(0);
      return;
    }

    if (reset) {
      setSearchResults([]);
      setFrom(0);
      setHasMore(true);
    }

    setIsLoading(true);
    const params = new URLSearchParams({
      q: query,
      from_: (reset ? 0 : from).toString(),
      exact: isExactMatch.toString(),
      sort_order: sortOrder,
      message_type: messageType,
    });
    const dateFromParam = combineDateTime(dateFrom, timeFrom, 'from');
    const dateToParam = combineDateTime(dateTo, timeTo, 'to');
    if (dateFromParam) params.append('date_from', dateFromParam);
    if (dateToParam) params.append('date_to', dateToParam);
    if (authorName) params.append('author_name', authorName);
    if (selectedVideoId) params.append('video_id', selectedVideoId);

    axios.get(`${API_BASE_URL}/search?${params.toString()}`)
      .then(response => {
        const { total, results } = response.data;
        if (results.length === 0) {
          setHasMore(false);
        } else {
          setSearchResults(prevResults => reset ? results : [...prevResults, ...results]);
          setFrom(prevFrom => prevFrom + results.length);
        }
        if (reset) {
          setTotalResults(total);
        }
      })
      .catch(error => {
        console.error("Error fetching search results:", error);
      })
      .finally(() => {
        setIsLoading(false);
      });
  }, [from, isExactMatch, dateFrom, dateTo, timeFrom, timeTo, hasActiveDateRange, authorName, selectedVideoId, sortOrder, messageType]);

  useEffect(() => {
    const handler = setTimeout(() => {
      debouncedSearch(searchQuery, true); // 新しい検索なのでリセット
    }, 500); // 500msのデバウンス

    return () => {
      clearTimeout(handler);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchQuery, isExactMatch, dateFrom, dateTo, timeFrom, timeTo, authorName, selectedVideoId, sortOrder, messageType]);

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

  const showContextAround = (result: SearchResult) => {
    // 既にピリオドモード中の場合は元の検索条件を上書きしない（連続タップ対応）
    setFilterSnapshot(prev => prev ?? {
      searchQuery,
      dateFrom,
      timeFrom,
      dateTo,
      timeTo,
      authorName,
      selectedVideoId,
      messageType,
      sortOrder,
    });

    const FIVE_MINUTES_MS = 5 * 60 * 1000;
    const windowStart = result.timestampSec - FIVE_MINUTES_MS;
    const windowEnd = result.timestampSec + FIVE_MINUTES_MS;

    setSearchQuery('');
    setAuthorName('');
    setMessageType('all');
    setSelectedVideoId(result.videoId);
    setDateFrom(formatDateInputValue(windowStart));
    setTimeFrom(formatTimeInputValue(windowStart));
    setDateTo(formatDateInputValue(windowEnd));
    setTimeTo(formatTimeInputValue(windowEnd));
    setSortOrder('asc');
  };

  const restoreSnapshot = () => {
    if (!filterSnapshot) return;
    setSearchQuery(filterSnapshot.searchQuery);
    setDateFrom(filterSnapshot.dateFrom);
    setTimeFrom(filterSnapshot.timeFrom);
    setDateTo(filterSnapshot.dateTo);
    setTimeTo(filterSnapshot.timeTo);
    setAuthorName(filterSnapshot.authorName);
    setSelectedVideoId(filterSnapshot.selectedVideoId);
    setMessageType(filterSnapshot.messageType);
    setSortOrder(filterSnapshot.sortOrder);
    setFilterSnapshot(null);
  };

  return (
    <div className="flex h-screen bg-slate-50 overflow-hidden">
      {/* Sidebar */}
      <aside className={`fixed inset-y-0 left-0 w-72 bg-white border-r border-slate-200 p-6 transform transition-transform duration-300 ease-in-out z-30 lg:relative lg:translate-x-0 ${isSidebarOpen ? 'translate-x-0' : '-translate-x-full'}`}>
        <div className="flex justify-between items-center mb-6">
          <h2 className="text-xl font-bold text-slate-800">フィルター</h2>
          <button onClick={() => setIsSidebarOpen(false)} className="lg:hidden text-slate-500 hover:text-slate-700">
            <svg className="w-6 h-6" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Date Filter */}
        <div className="space-y-4">
          <h3 className="text-sm font-semibold text-slate-600 uppercase">投稿日時</h3>
          <div>
            <label htmlFor="date-from" className="block text-sm font-medium text-slate-700 mb-1">From</label>
            <div className="flex flex-col gap-2">
              <input
                type="date"
                id="date-from"
                name="date-from"
                className="w-full px-3 py-2 border border-slate-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm"
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
              />
              <input
                type="time"
                id="time-from"
                name="time-from"
                className="w-full px-3 py-2 border border-slate-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm"
                value={timeFrom}
                onChange={(e) => setTimeFrom(e.target.value)}
              />
            </div>
          </div>
          <div>
            <label htmlFor="date-to" className="block text-sm font-medium text-slate-700 mb-1">To</label>
            <div className="flex flex-col gap-2">
              <input
                type="date"
                id="date-to"
                name="date-to"
                className="w-full px-3 py-2 border border-slate-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm"
                value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
              />
              <input
                type="time"
                id="time-to"
                name="time-to"
                className="w-full px-3 py-2 border border-slate-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm"
                value={timeTo}
                onChange={(e) => setTimeTo(e.target.value)}
              />
            </div>
          </div>
        </div>

        {/* Author Filter */}
        <div className="mt-8">
          <h3 className="text-sm font-semibold text-slate-600 uppercase mb-4">投稿者名</h3>
          <div className="relative">
            <input
              type="text"
              id="author-search"
              name="author-search"
              placeholder="投稿者名で検索..."
              className="w-full pl-10 pr-4 py-2 border border-slate-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm"
              value={authorName}
              onChange={(e) => setAuthorName(e.target.value)}
            />
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
              <svg className="w-4 h-4 text-slate-400" xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
            </div>
          </div>
        </div>

        {/* Video Filter Button */}
        <div className="mt-8">
          <h3 className="text-sm font-semibold text-slate-600 uppercase mb-4">動画で絞り込み</h3>
          <button
            onClick={() => setIsVideoFilterOpen(true)}
            className="w-full px-4 py-2 border border-slate-300 rounded-md shadow-sm text-sm font-medium text-slate-700 bg-white hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
          >
            {selectedVideoId ? '選択中の動画を変更' : '動画を選択'}
          </button>
          {selectedVideoId && (
            <div className="mt-4">
              <p className="text-sm text-slate-600 mb-2">選択中の動画:</p>
              <div className="flex items-center space-x-3">
                <img src={videos.find(v => v.videoId === selectedVideoId)?.thumbnail_url} alt="Selected thumbnail" className="w-16 h-auto rounded-md" />
                <p className="text-sm font-medium text-slate-800 flex-1">{videos.find(v => v.videoId === selectedVideoId)?.title}</p>
              </div>
              <button
                onClick={() => setSelectedVideoId(null)}
                className="mt-2 w-full text-sm text-center text-slate-600 hover:text-blue-600"
              >
                選択を解除
              </button>
            </div>
          )}
        </div>

        {/* External Links */}
        <div className="mt-8 pt-6 border-t border-slate-200 space-y-4">
          <a
            href="https://note.com/dapper_kalmia744/m/m308093b55d98"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center space-x-3 text-slate-600 hover:text-blue-600 transition-colors w-full"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 20H5a2 2 0 01-2-2V6a2 2 0 012-2h10a2 2 0 012 2v1m2 13a2 2 0 01-2-2V7m2 13a2 2 0 002-2V9a2 2 0 00-2-2h-2m-4-3H9M7 16h6M7 8h6v4H7V8z" />
            </svg>
            <span className="text-sm font-medium">お知らせ</span>
          </a>

          <a
            href="https://note.com/dapper_kalmia744/m/md4654ebd5871"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center space-x-3 text-slate-600 hover:text-blue-600 transition-colors w-full"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
            </svg>
            <span className="text-sm font-medium">開発者ブログ</span>
          </a>

          <button
            onClick={() => setIsInquiryOpen(true)}
            className="flex items-center space-x-3 text-slate-600 hover:text-blue-600 transition-colors w-full"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
            </svg>
            <span className="text-sm font-medium">お問い合わせ</span>
          </button>
        </div>
      </aside>

      {/* Overlay */}
      {isSidebarOpen && (
        <div
          className="fixed inset-0 bg-black bg-opacity-50 z-20 lg:hidden"
          onClick={() => setIsSidebarOpen(false)}
        ></div>
      )}

      {/* Main Content */}
      <main className="flex-1 overflow-y-auto">
        <div className="max-w-4xl mx-auto p-4 sm:p-6 lg:p-8">
          <header className="mb-8">
            <div className="flex items-center justify-between mb-2">
              <img src="/title.png" alt="うつログ❄️🖋️" className="block sm:h-[100px] w-auto h-[60px]" />
              <button onClick={() => setIsSidebarOpen(true)} className="lg:hidden text-slate-600 hover:text-slate-800">
                <svg className="w-6 h-6" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
                </svg>
              </button>
            </div>
            <div className="flex items-start justify-between">
              <p className="text-slate-600 lg:pl-0">Utsuro CH. 氷室うつろチャンネルの実況とチャットを検索できるよ。</p>
              <div className="flex items-center space-x-2">
                <button
                  onClick={() => setIsCautionOpen(true)}
                  className="text-slate-400 hover:text-slate-600 transition-colors"
                  title="注意書き"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor" className="w-6 h-6">
                    <path strokeLinecap="round" strokeLinejoin="round" d="m11.25 11.25.041-.02a.75.75 0 0 1 1.063.852l-.708 2.836a.75.75 0 0 0 1.063.853l.041-.021M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9-3.75h.008v.008H12V8.25Z" />
                  </svg>
                </button>
                <button
                  onClick={() => setIsHelpOpen(true)}
                  className="text-slate-400 hover:text-slate-600 transition-colors"
                  title="使い方"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor" className="w-6 h-6">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9.879 7.519c1.171-1.025 3.071-1.025 4.242 0 1.172 1.025 1.172 2.687 0 3.712-.203.179-.43.326-.67.442-.745.361-1.45.999-1.45 1.827v.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 5.25h.008v.008H12v-.008Z" />
                  </svg>
                </button>
              </div>
            </div>
            {/* Search Box */}
            <div className="mt-6 relative">
              <input
                type="text"
                placeholder="検索キーワードを入力（例: ミニうつろ）"
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
                  className="absolute top-full right-0 mt-2 w-[380px] bg-white border border-slate-200 rounded-lg shadow-xl z-20 p-4 max-h-[380px] overflow-y-auto"
                >
                  <h4 className="text-sm font-semibold text-slate-700 mb-3">カスタム絵文字</h4>
                  <div className="grid grid-cols-7 gap-1">
                    {customEmojis.filter(n => n.startsWith('_')).sort().map((fileName) => (
                      <button
                        key={fileName}
                        onClick={() => {
                          const emojiName = fileName.replace('.png', '');
                          setSearchQuery(prev => `${prev}${prev ? ' ' : ''}:${emojiName}:`);
                          setEmojiPickerOpen(false);
                        }}
                        className="p-0.5 rounded-md hover:bg-slate-100 transition-colors flex items-center justify-center h-10 w-10"
                        title={fileName.replace('.png', '')}
                      >
                        <img src={`/custom_emojis/${fileName}`} alt={fileName} className="max-w-full max-h-full object-contain" />
                      </button>
                    ))}

                    {customEmojis.some(n => n.startsWith('_')) && customEmojis.some(n => !n.startsWith('_')) && (
                      <div className="col-span-7 h-px bg-slate-200 my-2"></div>
                    )}

                    {customEmojis.filter(n => !n.startsWith('_')).sort().map((fileName) => (
                      <button
                        key={fileName}
                        onClick={() => {
                          const emojiName = fileName.replace('.png', '');
                          setSearchQuery(prev => `${prev}${prev ? ' ' : ''}:${emojiName}:`);
                          setEmojiPickerOpen(false);
                        }}
                        className="p-0.5 rounded-md hover:bg-slate-100 transition-colors flex items-center justify-center h-10 w-10"
                        title={fileName.replace('.png', '')}
                      >
                        <img src={`/custom_emojis/${fileName}`} alt={fileName} className="max-w-full max-h-full object-contain" />
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Control Row: Message Type & Exact Match */}
            <div className="flex flex-col sm:flex-row justify-between items-center mt-6 px-1 lg:px-0">
              {/* Message Type Segmented Control */}
              <div className="flex justify-start w-full sm:w-auto">
                <div className="bg-slate-200 p-1 rounded-full inline-flex relative shadow-inner w-full sm:w-auto">
                  {/* Sliding Background */}
                  <div
                    className={`absolute top-1 bottom-1 rounded-full bg-white shadow-sm transition-all duration-300 ease-in-out z-10`}
                    style={{
                      left: messageType === 'transcript' ? '0.25rem' : messageType === 'all' ? 'calc(33.333% + 0.25rem)' : 'calc(66.666% + 0.25rem)',
                      width: 'calc(33.333% - 0.5rem)'
                    }}
                  />

                  <button
                    onClick={() => setMessageType('transcript')}
                    className={`relative z-20 px-3 py-2 text-sm font-medium rounded-full transition-colors duration-200 focus:outline-none flex-1 min-w-[80px] sm:min-w-[100px] text-center ${messageType === 'transcript' ? 'text-blue-600' : 'text-slate-600 hover:text-slate-800'}`}
                  >
                    うつろ
                  </button>
                  <button
                    onClick={() => setMessageType('all')}
                    className={`relative z-20 px-3 py-2 text-sm font-medium rounded-full transition-colors duration-200 focus:outline-none flex-1 min-w-[80px] sm:min-w-[100px] text-center ${messageType === 'all' ? 'text-blue-600' : 'text-slate-600 hover:text-slate-800'}`}
                  >
                    すべて
                  </button>
                  <button
                    onClick={() => setMessageType('chat')}
                    className={`relative z-20 px-3 py-2 text-sm font-medium rounded-full transition-colors duration-200 focus:outline-none flex-1 min-w-[80px] sm:min-w-[100px] text-center ${messageType === 'chat' ? 'text-blue-600' : 'text-slate-600 hover:text-slate-800'}`}
                  >
                    チャット
                  </button>
                </div>
              </div>

              {/* Exact Match Toggle */}
              <div className="flex justify-end mt-4 sm:mt-0 w-full sm:w-auto">
                <label className="flex items-center space-x-2 cursor-pointer">
                  <input
                    type="checkbox"
                    className="rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                    checked={isExactMatch}
                    onChange={(e) => setIsExactMatch(e.target.checked)}
                  />
                  <span className="text-sm text-slate-600 whitespace-nowrap">完全一致で検索</span>
                </label>
              </div>
            </div>
          </header>

          {filterSnapshot && (
            <div className="sticky top-0 z-10 mb-4 px-4 py-3 bg-blue-50/95 border border-blue-200 rounded-md flex items-center justify-between gap-4">
              <p className="text-sm text-blue-800">
                期間表示中: {formatRangeLabel(dateFrom, timeFrom)} 〜 {formatRangeLabel(dateTo, timeTo)}
              </p>
              <button
                onClick={restoreSnapshot}
                className="text-sm font-medium text-blue-700 hover:text-blue-900 underline whitespace-nowrap"
              >
                元の検索に戻る
              </button>
            </div>
          )}

          {/* Search Results */}
          <section className="space-y-4">
            <div className="flex justify-between items-center">
              <h3 className="text-lg font-semibold text-slate-800">
                検索結果 ({totalResults.toLocaleString()}件)
              </h3>
              <button
                onClick={() => setSortOrder(prev => prev === 'desc' ? 'asc' : 'desc')}
                className="flex items-center space-x-1 text-sm text-slate-600 hover:text-blue-600 transition-colors"
              >
                <span>投稿日: {sortOrder === 'desc' ? '新しい順' : '古い順'}</span>
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  className={`w-4 h-4 transform transition-transform duration-200 ${sortOrder === 'asc' ? 'rotate-180' : ''}`}
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </button>
            </div>

            {searchResults.length > 0 ? (
              searchResults.map((result) => {
                const isChat = result.type === 'chat';
                return (
                  <div key={result.id} className={`relative group ${isChat ? 'pl-8 sm:pl-16' : 'pr-8 sm:pr-16'}`}>
                    <div className={`relative ${isChat ? 'rounded-sm' : 'rounded-xl'} overflow-hidden`}>
                      <div className="absolute inset-0 bg-cover bg-center bg-no-repeat filter grayscale" style={{ backgroundImage: `url(${result.thumbnailUrl})` }}></div>
                      <div className={`relative p-5 shadow-md border border-slate-200 hover:shadow-lg hover:border-blue-300 transition-all duration-200 ease-in-out ${isChat ? 'bg-white/95' : 'bg-blue-50/95'}`}>
                        <div className="flex items-center justify-between mb-3">
                          <div className="flex items-center space-x-3">
                            <img
                              src={`${result.authorIconUrl}`}
                              onError={(e) => {
                                e.currentTarget.src = `https://placehold.co/40x40/cbd5e1/475569?text=${result.author.charAt(0)}`;
                              }}
                              alt={`${result.author} Avatar`}
                              className="w-10 h-10 rounded-full"
                            />
                            <div>
                              <p className="font-semibold text-slate-800">{result.author}</p>
                              <p className="text-sm text-slate-500">動画: 「{result.videoTitle}」</p>
                              <p className="text-sm text-slate-500">投稿日: {formatDate(result.timestampSec)}</p>
                            </div>
                          </div>
                          <div className="flex flex-col items-center space-y-1">
                            <span className="text-sm font-medium text-slate-600 bg-slate-100 px-3 py-1 rounded-full">
                              {formatTimestamp(result.elapsedTime)}
                            </span>
                            <button
                              onClick={() => showContextAround(result)}
                              className="text-slate-400 hover:text-blue-600 transition-colors"
                              title="前後5分を表示"
                              aria-label="前後5分を表示"
                            >
                              <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor" className="w-4 h-4">
                                <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
                              </svg>
                            </button>
                          </div>
                        </div>
                        <p className="text-slate-700 leading-relaxed" dangerouslySetInnerHTML={{ __html: formatMessage(result.message, searchQuery) }} />
                      </div>
                    </div>
                    <div className="absolute left-1/2 -translate-x-1/2 bottom-full mb-3 w-64 opacity-0 invisible group-hover:opacity-100 group-hover:visible group-hover:bottom-full transition-all duration-200 ease-in-out z-20">
                      <div className="bg-black bg-opacity-90 text-white rounded-lg shadow-xl overflow-hidden">
                        <a href={`https://www.youtube.com/watch?v=${result.videoId}&t=${elapsedTimeSeconds(result.elapsedTime)}s`} target="_blank" rel="noopener noreferrer" className="text-xs text-blue-300 hover:text-blue-200 underline flex items-center space-x-1">
                          <img src={result.thumbnailUrl} alt={`Video thumbnail at ${formatTimestamp(result.elapsedTime)}`} className="w-full h-auto" />
                        </a>
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
                )
              })
            ) : (
              <div className="text-center py-12 text-slate-500">
                {isLoading ? '検索中...' : (searchQuery || authorName || selectedVideoId || hasActiveDateRange ? '検索結果が見つかりませんでした。' : '検索キーワードを入力してください。')}
              </div>
            )}
            {isLoading && <div className="text-center py-4">読み込み中...</div>}
            {!hasMore && searchResults.length > 0 && <div className="text-center py-4 text-slate-500">これ以上検索結果はありません。</div>}
          </section>
        </div>
      </main>

      <VideoFilter
        isOpen={isVideoFilterOpen}
        onClose={() => setIsVideoFilterOpen(false)}
        videos={videos}
        selectedVideoId={selectedVideoId}
        setSelectedVideoId={setSelectedVideoId}
      />

      <InquiryModal
        isOpen={isInquiryOpen}
        onClose={() => setIsInquiryOpen(false)}
      />

      <CautionModal
        isOpen={isCautionOpen}
        onClose={() => setIsCautionOpen(false)}
      />

      <HelpModal
        isOpen={isHelpOpen}
        onClose={() => setIsHelpOpen(false)}
      />
    </div>
  );
}

export default App;