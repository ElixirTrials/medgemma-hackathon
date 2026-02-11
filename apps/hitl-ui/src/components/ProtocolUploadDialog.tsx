import * as Dialog from '@radix-ui/react-dialog';
import { Loader2, Upload, X } from 'lucide-react';
import { type DragEvent, useCallback, useRef, useState } from 'react';

import { useUploadProtocol } from '../hooks/useProtocols';
import { cn } from '../lib/utils';
import { Button } from './ui/Button';

interface ProtocolUploadDialogProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
}

const MAX_FILE_SIZE = 50 * 1024 * 1024; // 50MB

export function ProtocolUploadDialog({ open, onOpenChange }: ProtocolUploadDialogProps) {
    const [selectedFile, setSelectedFile] = useState<File | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [dragOver, setDragOver] = useState(false);
    const fileInputRef = useRef<HTMLInputElement>(null);

    const uploadMutation = useUploadProtocol();

    const validateFile = useCallback((file: File): string | null => {
        if (file.type !== 'application/pdf') {
            return 'Only PDF files are accepted';
        }
        if (file.size > MAX_FILE_SIZE) {
            return 'File exceeds 50MB limit';
        }
        return null;
    }, []);

    const handleFileSelect = useCallback(
        (file: File) => {
            const validationError = validateFile(file);
            if (validationError) {
                setError(validationError);
                setSelectedFile(null);
                return;
            }
            setError(null);
            setSelectedFile(file);
        },
        [validateFile]
    );

    const handleInputChange = useCallback(
        (e: React.ChangeEvent<HTMLInputElement>) => {
            const file = e.target.files?.[0];
            if (file) {
                handleFileSelect(file);
            }
        },
        [handleFileSelect]
    );

    const handleDragOver = useCallback((e: DragEvent) => {
        e.preventDefault();
        setDragOver(true);
    }, []);

    const handleDragLeave = useCallback((e: DragEvent) => {
        e.preventDefault();
        setDragOver(false);
    }, []);

    const handleDrop = useCallback(
        (e: DragEvent) => {
            e.preventDefault();
            setDragOver(false);
            const file = e.dataTransfer.files[0];
            if (file) {
                handleFileSelect(file);
            }
        },
        [handleFileSelect]
    );

    const handleUpload = useCallback(async () => {
        if (!selectedFile) return;

        try {
            await uploadMutation.mutateAsync({ file: selectedFile });
            // Reset and close on success
            setSelectedFile(null);
            setError(null);
            onOpenChange(false);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Upload failed');
        }
    }, [selectedFile, uploadMutation, onOpenChange]);

    const handleOpenChange = useCallback(
        (nextOpen: boolean) => {
            if (!nextOpen) {
                setSelectedFile(null);
                setError(null);
            }
            onOpenChange(nextOpen);
        },
        [onOpenChange]
    );

    const formatFileSize = (bytes: number): string => {
        if (bytes < 1024) return `${bytes} B`;
        if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
        return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    };

    return (
        <Dialog.Root open={open} onOpenChange={handleOpenChange}>
            <Dialog.Portal>
                <Dialog.Overlay className="fixed inset-0 bg-black/50 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0" />
                <Dialog.Content className="fixed left-1/2 top-1/2 w-full max-w-lg -translate-x-1/2 -translate-y-1/2 rounded-lg border bg-background p-6 shadow-lg">
                    <div className="flex items-center justify-between mb-4">
                        <Dialog.Title className="text-lg font-semibold text-foreground">
                            Upload Protocol
                        </Dialog.Title>
                        <Dialog.Close asChild>
                            <button
                                type="button"
                                className="rounded-sm opacity-70 ring-offset-background transition-opacity hover:opacity-100 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
                                aria-label="Close"
                            >
                                <X className="h-4 w-4" />
                            </button>
                        </Dialog.Close>
                    </div>

                    <Dialog.Description className="text-sm text-muted-foreground mb-4">
                        Upload a clinical trial protocol PDF for analysis. Maximum file size: 50MB.
                    </Dialog.Description>

                    {/* Drop zone */}
                    <button
                        type="button"
                        className={cn(
                            'flex w-full flex-col items-center justify-center rounded-lg border-2 border-dashed p-8 transition-colors cursor-pointer',
                            dragOver
                                ? 'border-primary bg-primary/5'
                                : 'border-muted-foreground/25 hover:border-muted-foreground/50',
                            selectedFile && 'border-green-500 bg-green-500/5'
                        )}
                        onDragOver={handleDragOver}
                        onDragLeave={handleDragLeave}
                        onDrop={handleDrop}
                        onClick={() => fileInputRef.current?.click()}
                    >
                        <input
                            ref={fileInputRef}
                            type="file"
                            accept="application/pdf"
                            onChange={handleInputChange}
                            className="hidden"
                        />

                        {selectedFile ? (
                            <div className="text-center">
                                <Upload className="mx-auto h-8 w-8 text-green-500 mb-2" />
                                <p className="text-sm font-medium text-foreground">
                                    {selectedFile.name}
                                </p>
                                <p className="text-xs text-muted-foreground mt-1">
                                    {formatFileSize(selectedFile.size)}
                                </p>
                            </div>
                        ) : (
                            <div className="text-center">
                                <Upload className="mx-auto h-8 w-8 text-muted-foreground mb-2" />
                                <p className="text-sm text-muted-foreground">
                                    Drop PDF here or click to browse
                                </p>
                                <p className="text-xs text-muted-foreground mt-1">
                                    PDF files up to 50MB
                                </p>
                            </div>
                        )}
                    </button>

                    {/* Error message */}
                    {error && (
                        <p className="mt-3 text-sm text-destructive" role="alert">
                            {error}
                        </p>
                    )}

                    {/* Actions */}
                    <div className="mt-6 flex justify-end gap-3">
                        <Dialog.Close asChild>
                            <Button variant="outline" disabled={uploadMutation.isPending}>
                                Cancel
                            </Button>
                        </Dialog.Close>
                        <Button
                            onClick={handleUpload}
                            disabled={!selectedFile || uploadMutation.isPending}
                        >
                            {uploadMutation.isPending ? (
                                <>
                                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                    Uploading...
                                </>
                            ) : (
                                'Upload'
                            )}
                        </Button>
                    </div>
                </Dialog.Content>
            </Dialog.Portal>
        </Dialog.Root>
    );
}
