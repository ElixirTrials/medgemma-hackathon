import { Loader2 } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { pdfjs } from 'react-pdf';

interface TextBoundaryAdjusterProps {
    criterionText: string;
    pageNumber: number;
    pdfUrl: string;
    onChange: (newText: string) => void;
}

export default function TextBoundaryAdjuster({
    criterionText,
    pageNumber,
    pdfUrl,
    onChange,
}: TextBoundaryAdjusterProps) {
    const [pageText, setPageText] = useState<string | null>(null);
    const [words, setWords] = useState<string[]>([]);
    const [startIdx, setStartIdx] = useState(0);
    const [endIdx, setEndIdx] = useState(0);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [dragging, setDragging] = useState<'start' | 'end' | null>(null);

    const containerRef = useRef<HTMLDivElement>(null);

    // Extract text from the PDF page
    useEffect(() => {
        let cancelled = false;

        async function extractText() {
            setLoading(true);
            setError(null);

            try {
                const doc = await pdfjs.getDocument(pdfUrl).promise;
                const page = await doc.getPage(pageNumber);
                const content = await page.getTextContent();
                const text = content.items
                    .map((item) => ('str' in item ? item.str : ''))
                    .join(' ')
                    .replace(/\s+/g, ' ')
                    .trim();

                if (cancelled) return;

                setPageText(text);
                const wordArray = text.split(/\s+/);
                setWords(wordArray);

                // Find criterion text in page text using fuzzy substring match
                const normalizedCriterion = criterionText.replace(/\s+/g, ' ').trim();
                const normalizedPage = text;

                const matchPos = normalizedPage
                    .toLowerCase()
                    .indexOf(normalizedCriterion.toLowerCase());

                if (matchPos !== -1) {
                    // Count words before the match start
                    const beforeMatch = normalizedPage.substring(0, matchPos);
                    const wordsBeforeCount = beforeMatch.trim()
                        ? beforeMatch.trim().split(/\s+/).length
                        : 0;

                    // Count words in the criterion
                    const criterionWordCount = normalizedCriterion.split(/\s+/).length;

                    setStartIdx(wordsBeforeCount);
                    setEndIdx(wordsBeforeCount + criterionWordCount - 1);
                } else {
                    // Fallback: criterion text not found — show read-only
                    setError('Could not locate criterion text in page. Showing read-only view.');
                    setStartIdx(0);
                    setEndIdx(0);
                }
            } catch (_err) {
                if (cancelled) return;
                setError('Failed to extract page text.');
            } finally {
                if (!cancelled) setLoading(false);
            }
        }

        extractText();
        return () => {
            cancelled = true;
        };
    }, [pdfUrl, pageNumber, criterionText]);

    // Notify parent when selection changes
    useEffect(() => {
        if (words.length > 0 && !error) {
            const selectedText = words.slice(startIdx, endIdx + 1).join(' ');
            onChange(selectedText);
        }
    }, [startIdx, endIdx, words, error, onChange]);

    const handleMouseDown = useCallback(
        (handle: 'start' | 'end') => (e: React.MouseEvent) => {
            e.preventDefault();
            setDragging(handle);
        },
        []
    );

    // Handle mouse move during drag
    useEffect(() => {
        if (!dragging) return;

        function handleMouseMove(e: MouseEvent) {
            if (!containerRef.current) return;

            // Find the word element closest to the mouse position
            const wordEls = containerRef.current.querySelectorAll('[data-word-idx]');
            let closestIdx = -1;
            let closestDist = Number.POSITIVE_INFINITY;

            for (const el of wordEls) {
                const rect = el.getBoundingClientRect();
                const centerX = rect.left + rect.width / 2;
                const centerY = rect.top + rect.height / 2;
                const dist = Math.abs(e.clientX - centerX) + Math.abs(e.clientY - centerY);
                if (dist < closestDist) {
                    closestDist = dist;
                    closestIdx = Number.parseInt((el as HTMLElement).dataset.wordIdx ?? '-1', 10);
                }
            }

            if (closestIdx < 0) return;

            if (dragging === 'start') {
                // Can't go past end
                setStartIdx(Math.min(closestIdx, endIdx));
            } else {
                // Can't go before start
                setEndIdx(Math.max(closestIdx, startIdx));
            }
        }

        function handleMouseUp() {
            setDragging(null);
        }

        document.addEventListener('mousemove', handleMouseMove);
        document.addEventListener('mouseup', handleMouseUp);
        return () => {
            document.removeEventListener('mousemove', handleMouseMove);
            document.removeEventListener('mouseup', handleMouseUp);
        };
    }, [dragging, startIdx, endIdx]);

    if (loading) {
        return (
            <div className="flex items-center gap-2 py-4 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                Extracting page text...
            </div>
        );
    }

    if (error || !pageText) {
        return (
            <div className="rounded-lg border bg-muted/30 p-4">
                <p className="text-xs font-medium text-muted-foreground mb-2">
                    Text Boundary (read-only)
                </p>
                <p className="text-sm">{criterionText}</p>
                {error && <p className="text-xs text-amber-600 mt-1">{error}</p>}
            </div>
        );
    }

    // Determine context window: show ~30 words before and after selection
    const contextBefore = Math.max(0, startIdx - 30);
    const contextAfter = Math.min(words.length - 1, endIdx + 30);
    const displayWords = words.slice(contextBefore, contextAfter + 1);

    return (
        <div className="rounded-lg border bg-muted/30 p-4">
            <p className="text-xs font-medium text-muted-foreground mb-2">
                Source context (page {pageNumber}):
            </p>
            <div
                ref={containerRef}
                className="text-sm leading-relaxed select-none"
                style={{ userSelect: dragging ? 'none' : 'auto' }}
            >
                {contextBefore > 0 && <span className="text-muted-foreground">...</span>}
                {displayWords.map((word, i) => {
                    const globalIdx = contextBefore + i;
                    const isSelected = globalIdx >= startIdx && globalIdx <= endIdx;
                    const isStart = globalIdx === startIdx;
                    const isEnd = globalIdx === endIdx;

                    return (
                        <span key={globalIdx}>
                            {isStart && (
                                <span
                                    className="inline-flex items-center cursor-col-resize select-none text-blue-600 font-bold px-0.5"
                                    onMouseDown={handleMouseDown('start')}
                                    role="slider"
                                    aria-label="Drag to adjust selection start"
                                    aria-valuemin={0}
                                    aria-valuemax={endIdx}
                                    aria-valuenow={startIdx}
                                    tabIndex={0}
                                >
                                    |
                                </span>
                            )}
                            <span
                                data-word-idx={globalIdx}
                                className={
                                    isSelected
                                        ? 'bg-yellow-200 dark:bg-yellow-800/50 rounded px-0.5'
                                        : 'text-muted-foreground'
                                }
                            >
                                {word}
                            </span>
                            {isEnd && (
                                <span
                                    className="inline-flex items-center cursor-col-resize select-none text-blue-600 font-bold px-0.5"
                                    onMouseDown={handleMouseDown('end')}
                                    role="slider"
                                    aria-label="Drag to adjust selection end"
                                    aria-valuemin={startIdx}
                                    aria-valuemax={words.length - 1}
                                    aria-valuenow={endIdx}
                                    tabIndex={0}
                                >
                                    |
                                </span>
                            )}{' '}
                        </span>
                    );
                })}
                {contextAfter < words.length - 1 && (
                    <span className="text-muted-foreground">...</span>
                )}
            </div>
            <div className="mt-3 pt-2 border-t">
                <p className="text-xs font-medium text-muted-foreground mb-1">Selected:</p>
                <p className="text-sm bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded p-2">
                    {words.slice(startIdx, endIdx + 1).join(' ')}
                </p>
            </div>
        </div>
    );
}
