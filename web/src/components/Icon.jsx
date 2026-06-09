import React from 'react';
import * as LucideIcons from 'lucide-react';

export function Icon({ name, size = 16, strokeWidth = 1.75, className = '', style = {} }) {
  // Convert kebab-case names to PascalCase for lucide-react (e.g. shopping-cart -> ShoppingCart)
  const pascalName = name
    .split('-')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join('');
  
  const LucideIcon = LucideIcons[pascalName] || LucideIcons.HelpCircle;
  
  return (
    <LucideIcon 
      size={size} 
      strokeWidth={strokeWidth} 
      className={`lic ${className}`} 
      style={{ verticalAlign: 'middle', ...style }} 
    />
  );
}
