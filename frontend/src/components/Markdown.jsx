import { Streamdown } from 'streamdown';
import { code } from '@streamdown/code';
import { mermaid } from '@streamdown/mermaid';

export default function Markdown({ children, isAnimating = false }) {
  return (
    <div className="markdown-content">
      <Streamdown
        plugins={{ code, mermaid }}
        isAnimating={isAnimating}
        shikiTheme={['everforest-light', 'everforest-dark']}
        controls={{ code: true, table: true, mermaid: true }}
      >
        {children || ''}
      </Streamdown>
    </div>
  );
}
