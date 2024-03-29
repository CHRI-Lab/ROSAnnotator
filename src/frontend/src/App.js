import React from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import NavigationBar from './components/NavigationBar';
import Home from './pages/Home';
import About from './pages/About';

import 'bootstrap/dist/css/bootstrap.css';

function App() {

  const pages = [
    {name: 'Home', path: '/', page: <Home />},
    {name: 'About', path: '/about', page: <About />}
  ]

  return (
    <BrowserRouter>
      <NavigationBar pages={pages}/>
      <Routes>
        {pages.map((p) => {
          return <Route path={p.path} page={p.page} />
        })}
      </Routes>
    </BrowserRouter>
  );
}

export default App;
