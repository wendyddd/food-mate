import Image from "next/image";

interface LogoProps {
  /** 显示尺寸（宽高相等，单位 px） */
  size?: number;
  /** 附加 CSS 类名 */
  className?: string;
}

/**
 * FoodMate 品牌 Logo
 *
 * 参数:
 * size (number): 显示尺寸，默认 32
 * className (string): 附加样式类名
 *
 * 返回:
 * JSX.Element: Logo 图片元素
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
