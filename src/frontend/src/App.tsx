import React from "react";
import { BrowserRouter as Router, Routes, Route } from "react-router-dom";

import { LandingPage } from "./pages/Landing";
import Annotator from "./pages/Annotator";
import MainPage from "./pages/Main";
import LoadingPage from "./pages/Loading";

const App: React.FC = () => {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/main/:rosBagFile" element={<MainPage />} />
        <Route path="/main/:rosBagFile/:bookListFile" element={<MainPage />} />
        <Route path="/main/:rosBagFile/:bookListFile/:annotationFile" element={<MainPage />} />
        {/* Testing Routes */}
        <Route path="/loading" element={<LoadingPage />} />
        <Route path="/maintest" element={<Annotator />} />
      </Routes>
    </Router>
  );
};

export default App;
