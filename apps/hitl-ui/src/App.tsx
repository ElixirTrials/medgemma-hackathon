import { Route, Routes } from 'react-router-dom';

import Dashboard from './screens/Dashboard';
import ProtocolDetail from './screens/ProtocolDetail';
import ProtocolList from './screens/ProtocolList';
import ReviewPage from './screens/ReviewPage';
import ReviewQueue from './screens/ReviewQueue';

function App() {
    return (
        <div className="min-h-screen bg-background">
            <Routes>
                <Route path="/" element={<Dashboard />} />
                <Route path="/protocols" element={<ProtocolList />} />
                <Route path="/protocols/:id" element={<ProtocolDetail />} />
                <Route path="/reviews" element={<ReviewQueue />} />
                <Route path="/reviews/:batchId" element={<ReviewPage />} />
            </Routes>
        </div>
    );
}

export default App;
