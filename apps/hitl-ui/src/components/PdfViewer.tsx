import { ChevronLeft, ChevronRight, Loader2 } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { Document, Page, pdfjs } from 'react-pdf';
import 'react-pdf/dist/Page/TextLayer.css';
import 'react-pdf/dist/Page/AnnotationLayer.css';

import { Button } from './ui/Button';

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
    'pdfjs-dist/build/pdf.worker.min.mjs',
    import.meta.url
).toString();

interface PdfViewerProps {
    url: string;
    targetPage?: number | null;    // Page to scroll to (1-based)
    highlightText?: string | null;  // Text to highlight on the target page
}

export default function PdfViewer({ url, targetPage, highlightText }: PdfViewerProps) {
    const [numPages, setNumPages] = useState<number | null>(null);
    const [pageNumber, setPageNumber] = useState(1);
    const [loadError, setLoadError] = useState<string | null>(null);
    const [flashKey, setFlashKey] = useState(0);

    function onDocumentLoadSuccess({ numPages }: { numPages: number }) {
        setNumPages(numPages);
        setLoadError(null);
    }

    function onDocumentLoadError(error: Error) {
        setLoadError(error.message || 'Failed to load PDF');
    }

    // Navigate to targetPage when it changes
    useEffect(() => {
        if (targetPage && targetPage >= 1 && numPages && targetPage <= numPages) {
            setPageNumber(targetPage);
            setFlashKey(prev => prev + 1);
        }
    }, [targetPage, numPages]);

    // Custom text renderer for highlighting
    const textRenderer = useCallback(
        (textItem: { str: string }) => {
            if (!highlightText || pageNumber !== targetPage) {
                return textItem.str;
            }
            // Case-insensitive search for highlight text within this text item
            const lowerStr = textItem.str.toLowerCase();
            const lowerHighlight = highlightText.toLowerCase();
            // Only attempt highlight if the text item contains part of the search
            // Use first 40 chars of highlightText for matching (criteria text can be very long)
            const searchSnippet = lowerHighlight.slice(0, 40);
            if (searchSnippet && lowerStr.includes(searchSnippet)) {
                const startIdx = lowerStr.indexOf(searchSnippet);
                const before = textItem.str.slice(0, startIdx);
                const match = textItem.str.slice(startIdx, startIdx + searchSnippet.length);
                const after = textItem.str.slice(startIdx + searchSnippet.length);
                return `${before}<mark class="bg-yellow-200/80">${match}</mark>${after}`;
            }
            return textItem.str;
        },
        [highlightText, pageNumber, targetPage]
    );

    return (
        <div className="h-full flex flex-col">
            <style>{`
                .react-pdf__Page__textContent mark {
                    background-color: rgb(254 240 138 / 0.8);
                    padding: 0 2px;
                    border-radius: 2px;
                }
            `}</style>
            <div className="flex-1 overflow-auto flex justify-center bg-muted/30 p-4">
                {loadError ? (
                    <div className="flex items-center justify-center h-full">
                        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-6 text-center">
                            <p className="text-sm text-destructive">
                                Failed to load PDF: {loadError}
                            </p>
                        </div>
                    </div>
                ) : (
                    <Document
                        file={url}
                        onLoadSuccess={onDocumentLoadSuccess}
                        onLoadError={onDocumentLoadError}
                        loading={
                            <div className="flex items-center justify-center h-64">
                                <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                            </div>
                        }
                    >
                        <div key={flashKey}>
                            <Page
                                pageNumber={pageNumber}
                                width={500}
                                customTextRenderer={textRenderer}
                            />
                        </div>
                    </Document>
                )}
            </div>

            {/* Page navigation controls */}
            {numPages !== null && (
                <div className="flex items-center justify-center gap-4 border-t bg-card px-4 py-3">
                    <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setPageNumber((p) => Math.max(1, p - 1))}
                        disabled={pageNumber <= 1}
                    >
                        <ChevronLeft className="h-4 w-4" />
                    </Button>
                    <span className="text-sm text-muted-foreground">
                        Page {pageNumber} of {numPages}
                    </span>
                    <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setPageNumber((p) => Math.min(numPages, p + 1))}
                        disabled={pageNumber >= numPages}
                    >
                        <ChevronRight className="h-4 w-4" />
                    </Button>
                </div>
            )}
        </div>
    );
}
