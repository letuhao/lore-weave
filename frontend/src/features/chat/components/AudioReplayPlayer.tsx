/**
 * AudioReplayPlayer — play/pause + progress bar for message audio segments.
 * Fetches segment URLs lazily on first play, plays sequentially.
 *
 * Design ref: VOICE_PIPELINE_V2.md §8.1
 */
import { useState, useRef, useCallback, useEffect } from 'react';
import { Play, Pause, Volume2 } from 'lucide-react';
import { useAuth } from '@/auth';
import { cn } from '@/lib/utils';

interface AudioSegment {
  index: number;
  text: string;
  durationS: number | null;
  url: string;
}

interface AudioReplayPlayerProps {
  sessionId: string;
  messageId: string;
}

export function AudioReplayPlayer({ sessionId, messageId }: AudioReplayPlayerProps) {
  const { accessToken } = useAuth();
  const [segments, setSegments] = useState<AudioSegment[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [expanded, setExpanded] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const fetchSegments = useCallback(async () => {
    if (segments || !accessToken) return segments;
    setLoading(true);
    try {
      const apiBase = import.meta.env.VITE_API_BASE || '';
      const resp = await fetch(
        `${apiBase}/v1/chat/sessions/${sessionId}/messages/${messageId}/audio-segments`,
        { headers: { Authorization: `Bearer ${accessToken}` } },
      );
      if (!resp.ok) return null;
      const data = await resp.json();
      setSegments(data.segments);
      return data.segments as AudioSegment[];
    } catch {
      return null;
    } finally {
      setLoading(false);
    }
  }, [sessionId, messageId, accessToken, segments]);

  const playSegment = useCallback((segs: AudioSegment[], index: number) => {
    if (index >= segs.length) {
      setPlaying(false);
      setCurrentIndex(0);
      return;
    }
    setCurrentIndex(index);
    const audio = new Audio(segs[index].url);
    audioRef.current = audio;
    audio.onended = () => playSegment(segs, index + 1);
    audio.onerror = () => playSegment(segs, index + 1);
    audio.play().catch(() => setPlaying(false));
  }, []);

  const handleToggle = useCallback(async () => {
    if (playing) {
      audioRef.current?.pause();
      setPlaying(false);
      return;
    }
    const segs = await fetchSegments();
    if (!segs || segs.length === 0) return;
    setPlaying(true);
    playSegment(segs, 0);
  }, [playing, fetchSegments, playSegment]);

  const handleSegmentClick = useCallback(async (index: number) => {
    const segs = segments || await fetchSegments();
    if (!segs) return;
    audioRef.current?.pause();
    setPlaying(true);
    playSegment(segs, index);
  }, [segments, fetchSegments, playSegment]);

  // Cleanup on unmount
  useEffect(() => {
    return () => { audioRef.current?.pause(); };
  }, []);

  const totalDuration = segments?.reduce((sum, s) => sum + (s.durationS ?? 0), 0) ?? 0;

  return (
    <div className="mt-1">
      {/* Main play/pause row */}
      <div className="flex items-center gap-2">
        <Volume2 className="h-3.5 w-3.5 text-muted-foreground" />
        <button
          onClick={handleToggle}
          disabled={loading}
          className="rounded p-1 text-muted-foreground hover:text-foreground transition-colors"
          aria-label={playing ? 'Pause' : 'Play'}
        >
          {playing ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
        </button>

        {segments && segments.length > 0 && (
          <>
            {/* Simple progress indicator */}
            <span className="text-[10px] text-muted-foreground">
              {playing ? `${currentIndex + 1}/${segments.length}` : `${segments.length} segments`}
            </span>
            {totalDuration > 0 && (
              <span className="text-[10px] text-muted-foreground">
                {Math.round(totalDuration)}s
              </span>
            )}
            {/* Expand/collapse per-sentence buttons */}
            {segments.length > 1 && (
              <button
                onClick={() => setExpanded(!expanded)}
                className="text-[10px] text-muted-foreground hover:text-foreground"
              >
                {expanded ? 'collapse' : `${segments.length} segments`}
              </button>
            )}
          </>
        )}
      </div>

      {/* Per-segment buttons (collapsed by default) */}
      {expanded && segments && (
        <div className="mt-1 flex flex-wrap gap-1">
          {segments.map((seg) => (
            <button
              key={seg.index}
              onClick={() => handleSegmentClick(seg.index)}
              className={cn(
                'rounded border px-2 py-0.5 text-[10px] transition-colors',
                currentIndex === seg.index && playing
                  ? 'border-primary bg-primary/10 text-primary'
                  : 'border-border text-muted-foreground hover:text-foreground',
              )}
              title={seg.text}
            >
              S{seg.index + 1} {seg.durationS ? `${seg.durationS.toFixed(1)}s` : ''}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
