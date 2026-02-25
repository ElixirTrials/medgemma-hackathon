import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react-swc';
import path from 'path';

export default defineConfig(({ mode }) => {
    void mode;
    const rawBasePath = process.env.BASE_PATH ?? '/demo-app/';
    const trimmedBasePath = rawBasePath.trim();
    const withLeadingSlash = trimmedBasePath
        ? trimmedBasePath.startsWith('/')
            ? trimmedBasePath
            : `/${trimmedBasePath}`
        : '/';
    const normalizedBasePath = withLeadingSlash.endsWith('/')
        ? withLeadingSlash
        : `${withLeadingSlash}/`;
    // Router basename: no trailing slash; root path is '/' (React Router expects '/' for root)
    const routerBasename = normalizedBasePath.replace(/\/$/, '') || '/';
    return {
        plugins: [react()],
        base: normalizedBasePath,
        define: {
            __ROUTER_BASENAME__: JSON.stringify(routerBasename),
        },
        resolve: {
            extensions: ['.js', '.jsx', '.ts', '.tsx', '.json'],
            alias: {
                '@': path.resolve(__dirname, './src'),
            },
        },
        build: {
            target: 'esnext',
            outDir: 'build',
            chunkSizeWarningLimit: 800,
        },
        server: {
            port: 3000,
            open: normalizedBasePath,
        },
        test: {
            globals: true,
            environment: 'jsdom',
            setupFiles: './src/test/setup.ts',
            exclude: ['e2e/**', 'node_modules/**'],
            pool: 'threads',
            css: true,
            coverage: {
                provider: 'v8',
                reporter: ['text', 'json', 'html'],
                exclude: [
                    'node_modules/',
                    'src/test/',
                    '**/*.d.ts',
                    '**/*.config.*',
                    '**/mock*.ts',
                    '**/*.test.*',
                    '**/*.spec.*',
                ],
                thresholds: {
                    lines: 85,
                    functions: 85,
                    branches: 80,
                    statements: 85,
                },
            },
        },
    };
});
