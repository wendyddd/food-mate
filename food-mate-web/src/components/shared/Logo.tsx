import Image from "next/image";

interface LogoProps {
  /** Display size (equal width and height, in px) */
  size?: number;
  /** Extra CSS class names */
  className?: string;
}

/**
 * FoodMate brand logo
 *
 * @param size - Display size, default 32
 * @param className - Extra CSS class names
 * @returns Logo image element
 */
export default function Logo({ size = 32, className = "" }: LogoProps) {
  return (
    <Image
      src="/logo.png"
      alt="FoodMate"
      width={size}
      height={size}
      className={`object-contain ${className}`}
      priority
    />
  );
}
