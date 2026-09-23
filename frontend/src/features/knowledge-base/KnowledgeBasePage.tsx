import { Database, FileText, Search } from 'lucide-react';
import { useSearchParams } from 'react-router-dom';
import { PageContainer } from '@/components/layout/PageContainer';
import { Tabs, type TabItem } from '@/components/ui/Tabs';
import { DocumentsTab } from './DocumentsTab';
import { SchemaTab } from './SchemaTab';
import { SearchTab } from './SearchTab';

type TabId = 'documents' | 'search' | 'schema';

const TABS: TabItem<TabId>[] = [
  { id: 'documents', label: 'Documents', icon: <FileText className="size-4" aria-hidden /> },
  { id: 'search', label: 'Search', icon: <Search className="size-4" aria-hidden /> },
  { id: 'schema', label: 'Database Schema', icon: <Database className="size-4" aria-hidden /> },
];

function isTab(value: string | null): value is TabId {
  return value === 'documents' || value === 'search' || value === 'schema';
}

export function KnowledgeBasePage() {
  const [params, setParams] = useSearchParams();
  const raw = params.get('tab');
  const tab: TabId = isTab(raw) ? raw : 'documents';

  return (
    <PageContainer
      title="Knowledge Base"
      description="Documents the agent can cite, retrieval testing, and the database it can query."
    >
      <Tabs
        items={TABS}
        value={tab}
        onChange={(id) => setParams({ tab: id }, { replace: true })}
        label="Knowledge base sections"
      >
        {tab === 'documents' && <DocumentsTab />}
        {tab === 'search' && <SearchTab />}
        {tab === 'schema' && <SchemaTab />}
      </Tabs>
    </PageContainer>
  );
}
