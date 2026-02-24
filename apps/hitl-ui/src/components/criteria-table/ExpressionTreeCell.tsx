interface ExpressionNode {
    type: string;
    entity?: string;
    relation?: string;
    value?: string;
    unit?: string;
    children?: ExpressionNode[];
}

interface ExpressionTreeCellProps {
    tree: Record<string, unknown> | null;
    expanded?: boolean;
}

function NodeBadge({ type }: { type: string }) {
    const colors: Record<string, string> = {
        AND: 'bg-purple-100 text-purple-700 border-purple-300',
        OR: 'bg-blue-100 text-blue-700 border-blue-300',
        NOT: 'bg-red-100 text-red-700 border-red-300',
        ATOMIC: 'bg-gray-100 text-gray-700 border-gray-300',
    };

    return (
        <span
            className={`inline-flex items-center rounded border px-1 py-0 text-[10px] font-bold ${colors[type] || colors.ATOMIC}`}
        >
            {type}
        </span>
    );
}

function TreeNode({ node, depth = 0 }: { node: ExpressionNode; depth?: number }) {
    const indent = depth * 16;

    if (node.type === 'ATOMIC') {
        return (
            <div className="flex items-center gap-1 text-xs" style={{ paddingLeft: indent }}>
                <span className="text-muted-foreground">&#x25cf;</span>
                <span className="font-medium">{node.entity || '?'}</span>
                {node.relation && <span className="text-blue-600 font-mono">{node.relation}</span>}
                {node.value && <span>{node.value}</span>}
                {node.unit && <span className="text-muted-foreground">{node.unit}</span>}
            </div>
        );
    }

    return (
        <div style={{ paddingLeft: indent }}>
            <NodeBadge type={node.type} />
            {node.children?.map((child, i) => (
                // biome-ignore lint/suspicious/noArrayIndexKey: tree nodes have no stable id
                <TreeNode key={i} node={child as ExpressionNode} depth={depth + 1} />
            ))}
        </div>
    );
}

export function ExpressionTreeCell({ tree, expanded = false }: ExpressionTreeCellProps) {
    if (!tree) return <span className="text-muted-foreground text-xs italic">—</span>;

    const root = (tree.root || tree) as ExpressionNode;

    if (!expanded && root.type !== 'ATOMIC') {
        const childCount = root.children?.length || 0;
        return (
            <div className="flex items-center gap-1">
                <NodeBadge type={root.type} />
                <span className="text-xs text-muted-foreground">({childCount} children)</span>
            </div>
        );
    }

    return (
        <div className="space-y-0.5">
            <TreeNode node={root} />
        </div>
    );
}
