// App.tsx
import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import MainContent from './pages/mainContent';
import LoadableList from './pages/load';
const App: React.FC = () => {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<MainContent />} />
        <Route path="/load" element={<LoadableList/>} />
        {/* You can add more routes here if needed */}
      </Routes>
    </Router>
  );
};

export default App;
