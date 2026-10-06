import type { Element, Root, RootContent } from 'hast'

function hasClass(element: Element, name: string) {
  const { className } = element.properties
  return Array.isArray(className) && className.includes(name)
}

function isDisplayMath(node: RootContent) {
  return (
    node.type === 'element' &&
    node.tagName === 'pre' &&
    node.children.some(
      (child) =>
        child.type === 'element' &&
        child.tagName === 'code' &&
        hasClass(child, 'math-display'),
    )
  )
}

function wrapDisplayMath(parent: Root | Element) {
  parent.children = parent.children.map((child) => {
    if (child.type !== 'element') return child
    const start = child.position?.start.line
    const end = child.position?.end.line
    if (isDisplayMath(child) && start && end) {
      return {
        type: 'element',
        tagName: 'div',
        properties: {
          dataSourceStartLine: String(start),
          dataSourceEndLine: String(end),
        },
        children: [child],
      } satisfies Element
    }
    wrapDisplayMath(child)
    return child
  })
}

// rehype-katex replaces a display-math <pre> with a bare <span class="katex-display">,
// which drops its Markdown source position. Wrapping the <pre> first keeps that
// position on a surviving ancestor so the equation can still be annotated.
// Run this after rehype-raw and before rehype-katex.
export function rehypeDisplayMathPosition() {
  return (tree: Root) => wrapDisplayMath(tree)
}
