import { ChevronLeft, ChevronRight, Loader2 } from 'lucide-react';
import { useState } from 'react';
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
}

export default function PdfViewer({ url }: PdfViewerProps) {
    const [numPages, setNumPages] = useState<number | null>(null);
    const [pageNumber, setPageNumber] = useState(1);
    const [loadError, setLoadError] = useState<string | null>(null);

    function onDocumentLoadSuccess({ numPages }: { numPages: number }) {
        setNumPages(numPages);
        setLoadError(null);
    }

    function onDocumentLoadError(error: Error) {
        setLoadError(error.message || 'Failed to load PDF');
    }

    return (
        <div className="h-full flex flex-col">
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
                        <Page pageNumber={pageNumber} width={500} />
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
