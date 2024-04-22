import React from 'react';
import { styled } from '@mui/system';

// Props 类型定义
interface BlockProps {
  block: { start: number; end: number };
  duration: number;
  isSelected: boolean;
  onSelect: () => void;
}

// 组件样式
const NewBlock = styled('div')(({ theme }) => ({
  position: 'absolute',
  height: '100%',
  backgroundColor: theme.palette.action.selected,
}));

// Block 组件
const Block: React.FC<BlockProps> = ({ block, duration, isSelected, onSelect }) => {
  return (
    <NewBlock
      onClick={onSelect}
      style={{
        left: `${(block.start / duration) * 100}%`,
        width: `${((block.end - block.start) / duration) * 100}%`,
        backgroundColor: isSelected ? 'red' : 'grey',
      }}
    />
  );
};

export default Block;
