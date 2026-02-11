import { Route, Routes } from 'react-router-dom';

import Dashboard from './screens/Dashboard';
import ProtocolDetail from './screens/ProtocolDetail';
import ProtocolList from './screens/ProtocolList';

function App() {
    return (
        <div className="min-h-screen bg-background">
            <Routes>
                <Route path="/" element={<Dashboard />} />
                <Route path="/protocols" element={<ProtocolList />} />
                <Route path="/protocols/:id" element={<ProtocolDetail />} />
            </Routes>
        </div>
    );
}

export default App;
