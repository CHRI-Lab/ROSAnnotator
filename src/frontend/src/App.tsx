import React from "react";
import { BrowserRouter as Router, Routes, Route } from "react-router-dom";
import Annotator from "./pages/Annotator";
import LoadableList from "./pages/Load";
import LoadingPage from "./pages/Loading";

const App: React.FC = () => {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<Annotator />} />
        <Route path="/load" element={<LoadableList />} />
        <Route path="/loading" element={<LoadingPage />} />
      </Routes>
    </Router>
  );
};

export default App;
