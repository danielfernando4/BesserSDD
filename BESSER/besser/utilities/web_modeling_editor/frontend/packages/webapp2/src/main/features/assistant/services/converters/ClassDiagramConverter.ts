/**
 * Class Diagram Converter
 * Converts simplified class specifications to Apollon format
 */

import { DiagramConverter, PositionGenerator, generateUniqueId } from './base';
import { normalizeType } from '../shared/typeNormalization';

export class ClassDiagramConverter implements DiagramConverter {
  private positionGenerator = new PositionGenerator();

  getDiagramType() {
    return 'ClassDiagram' as const;
  }

  convertSingleElement(spec: any, position?: { x: number; y: number }, classNames?: Set<string>) {
    const pos = position || this.positionGenerator.getNextPosition();
    const classId = generateUniqueId('class');
    
    const baseHeight = 60;
    const attrHeight = (spec.attributes?.length || 0) * 25 + (spec.attributes?.length > 0 ? 10 : 0);
    const methodHeight = (spec.methods?.length || 0) * 25 + (spec.methods?.length > 0 ? 10 : 0);
    const totalHeight = baseHeight + attrHeight + methodHeight;
    
    const classElement: any = {
      type: "Class",
      id: classId,
      name: spec.className,
      owner: null,
      bounds: { x: pos.x, y: pos.y, width: 220, height: totalHeight },
      attributes: [] as string[],
      methods: [] as string[]
    };

    if (spec.isAbstract) {
      classElement.type = 'AbstractClass';
      classElement.italic = true;
      classElement.stereotype = 'abstract';
    }

    if (spec.isEnumeration) {
      classElement.type = 'Enumeration';
      classElement.stereotype = 'enumeration';
    }

    if (spec.isInterface) {
      classElement.type = 'Interface';
      classElement.italic = true;
      classElement.stereotype = 'interface';
    }
    
    const { attributes, endY: attrEndY } = this.createAttributes(spec, classId, pos.y + 50, pos.x, classNames);
    const { methods } = this.createMethods(spec, classId, attrEndY, pos.x);
    
    classElement.attributes = Object.keys(attributes);
    classElement.methods = Object.keys(methods);
    
    return {
      class: classElement,
      attributes,
      methods
    };
  }

  convertCompleteSystem(systemSpec: any) {
    this.positionGenerator.reset();
    const allElements: Record<string, any> = {};
    const allRelationships: Record<string, any> = {};
    const classIdMap: Record<string, string> = {};

    // Collect all class/enum names so attribute types can reference them
    const allClassNames = new Set<string>();
    systemSpec.classes?.forEach((c: any) => { if (c.className) allClassNames.add(c.className); });

    systemSpec.classes?.forEach((classSpec: any) => {
      const position = classSpec.position || this.positionGenerator.getNextPosition();
      const completeElement = this.convertSingleElement(classSpec, position, allClassNames);
      classIdMap[classSpec.className] = completeElement.class.id;

      allElements[completeElement.class.id] = completeElement.class;
      Object.assign(allElements, completeElement.attributes);
      Object.assign(allElements, completeElement.methods);
    });
    
    systemSpec.relationships?.forEach((rel: any) => {
      const sourceId = classIdMap[rel.sourceClass || rel.source];
      const targetId = classIdMap[rel.targetClass || rel.target];
      
      if (sourceId && targetId) {
        const relId = generateUniqueId('rel');
        const relationshipType = this.getRelationshipType(rel.type);
        
        allRelationships[relId] = {
          id: relId,
          type: relationshipType,
          source: { 
            element: sourceId,
            direction: rel.sourceDirection || 'Left',
            multiplicity: rel.sourceMultiplicity || '1',
            role: '',
            bounds: { x: 0, y: 0, width: 0, height: 0 }
          },
          target: { 
            element: targetId,
            direction: rel.targetDirection || 'Right',
            multiplicity: rel.targetMultiplicity || '1',
            role: rel.name || '',
            bounds: { x: 0, y: 0, width: 0, height: 0 }
          },
          bounds: { x: 0, y: 0, width: 0, height: 0 },
          name: rel.name || '',
          path: [{ x: 100, y: 10 }, { x: 0, y: 10 }],
          isManuallyLayouted: false
        };
      }
    });
    
    return {
      version: "3.0.0",
      type: "ClassDiagram",
      size: { width: 1400, height: 740 },
      elements: allElements,
      relationships: allRelationships,
      interactive: { elements: {}, relationships: {} },
      assessments: {}
    };
  }

  private createAttributes(spec: any, classId: string, startY: number, startX: number, classNames?: Set<string>) {
    const attributes: Record<string, any> = {};
    let currentY = startY;

    spec.attributes?.forEach((attr: any) => {
      const attrId = generateUniqueId('attr');
      const visibility = attr.visibility || 'public';
      const normalizedType = normalizeType(attr.type, classNames);
      
      const attrElement: any = {
        id: attrId,
        name: attr.name,
        type: "ClassAttribute",
        owner: classId,
        bounds: { x: startX + 1, y: currentY, width: 218, height: 25 },
        visibility: visibility,
        attributeType: normalizedType,
      };

      if (attr.isDerived) {
        attrElement.isDerived = true;
      }
      if (attr.defaultValue !== undefined && attr.defaultValue !== null) {
        attrElement.defaultValue = attr.defaultValue;
      }
      if (attr.isOptional) {
        attrElement.isOptional = true;
      }

      attributes[attrId] = attrElement;
      
      currentY += 25;
    });
    
    return { attributes, endY: currentY };
  }

  private createMethods(spec: any, classId: string, startY: number, startX: number) {
    const methods: Record<string, any> = {};
    let currentY = startY + ((spec.attributes?.length || 0) > 0 ? 10 : 0);
    
    spec.methods?.forEach((method: any) => {
      const methodId = generateUniqueId('method');
      const visibilitySymbol = method.visibility === 'public' ? '+' : 
                             method.visibility === 'private' ? '-' : '#';
      
      const paramStr = method.parameters?.map((p: any) => p.type ? `${p.name}: ${normalizeType(p.type)}` : p.name).join(', ') || '';
      const rawReturn = (method.returnType || 'void').replace(/^:+/, '');  // Strip leading colons
      const normalizedReturnType = normalizeType(rawReturn);
      // Strip any signature artifacts from the method name (LLM sometimes embeds params/return in name)
      const cleanMethodName = (method.name || 'method').replace(/\(.*\).*$/, '').trim();

      // Use explicit new-format fields so Apollon's deserializer doesn't
      // need to parse the signature string (which splits at the wrong colon).
      const methodElement: any = {
        id: methodId,
        name: `${cleanMethodName}(${paramStr})`,
        type: "ClassMethod",
        owner: classId,
        bounds: { x: startX + 1, y: currentY, width: 218, height: 25 },
        visibility: method.visibility || 'public',
        attributeType: normalizedReturnType,
      };

      if (method.code) {
        methodElement.code = method.code;
        if (!method.implementationType) {
          methodElement.implementationType = 'code';
        }
      }

      if (method.implementationType) {
        methodElement.implementationType = method.implementationType;
      }

      methods[methodId] = methodElement;
      
      currentY += 25;
    });
    
    return { methods, endY: currentY };
  }

  private getRelationshipType(type: string): string {
    switch (type?.toLowerCase()) {
      case 'inheritance':
      case 'generalization':
        return 'ClassInheritance';
      case 'composition':
        return 'ClassComposition';
      case 'aggregation':
        return 'ClassAggregation';
      default:
        return 'ClassBidirectional';
    }
  }

  /**
   * Reverse-convert: UMLModel (Apollon format) → SystemClassSpec JSON.
   *
   * This enables the "diagram → requirements" direction of bidirectional
   * traceability. When the user edits the canvas directly, we extract the
   * current state as a SystemClassSpec that the SDD pipeline agents
   * (DesignAgent, TraceabilityAgent, RequirementsAgent) understand.
   */
  static reverseConvert(umlModel: any): any {
    if (!umlModel || !umlModel.elements) {
      return { systemName: 'System', classes: [], relationships: [] };
    }

    const elements = umlModel.elements || {};
    const relationships = umlModel.relationships || {};

    // Identify class-level elements (Class, AbstractClass, Enumeration, Interface)
    const classTypes = new Set(['Class', 'AbstractClass', 'Enumeration', 'Interface']);
    const classElements: Record<string, any> = {};
    const childElements: Record<string, any> = {};

    for (const [id, el] of Object.entries<any>(elements)) {
      if (classTypes.has(el.type)) {
        classElements[id] = el;
      } else if (el.owner) {
        if (!childElements[el.owner]) childElements[el.owner] = [];
        childElements[el.owner].push(el);
      }
    }

    // Build classes array
    const classes: any[] = [];
    const idToName: Record<string, string> = {};

    for (const [id, el] of Object.entries<any>(classElements)) {
      idToName[id] = el.name || 'UnnamedClass';

      const children = childElements[id] || [];
      const attributes: any[] = [];
      const methods: any[] = [];

      for (const child of children) {
        if (child.type === 'ClassAttribute') {
          const attr: any = {
            name: child.name || 'unnamed',
            type: child.attributeType || 'String',
            visibility: child.visibility || 'public',
          };
          attributes.push(attr);
        } else if (child.type === 'ClassMethod') {
          // Parse method name — may be in "methodName(params)" format
          let methodName = child.name || 'method';
          const paramList: any[] = [];

          const parenMatch = methodName.match(/^([^(]+)\(([^)]*)\)/);
          if (parenMatch) {
            methodName = parenMatch[1].trim();
            const paramStr = parenMatch[2].trim();
            if (paramStr) {
              paramStr.split(',').forEach((p: string) => {
                const parts = p.trim().split(':').map((s: string) => s.trim());
                paramList.push({
                  name: parts[0] || 'arg',
                  type: parts[1] || 'String',
                });
              });
            }
          }

          methods.push({
            name: methodName,
            returnType: child.attributeType || 'void',
            visibility: child.visibility || 'public',
            parameters: paramList,
          });
        }
      }

      classes.push({
        className: el.name || 'UnnamedClass',
        attributes,
        methods,
        isAbstract: el.type === 'AbstractClass',
        isEnumeration: el.type === 'Enumeration',
      });
    }

    // Build relationships array
    const rels: any[] = [];

    for (const [, rel] of Object.entries<any>(relationships)) {
      const sourceId = rel.source?.element;
      const targetId = rel.target?.element;
      const sourceName = idToName[sourceId];
      const targetName = idToName[targetId];

      if (!sourceName || !targetName) continue;

      const relType = ClassDiagramConverter.reverseRelationshipType(rel.type);

      rels.push({
        type: relType,
        source: sourceName,
        target: targetName,
        sourceMultiplicity: rel.source?.multiplicity || '1',
        targetMultiplicity: rel.target?.multiplicity || '1',
        name: rel.name || rel.target?.role || '',
      });
    }

    return {
      systemName: 'System',
      classes,
      relationships: rels,
    };
  }

  /**
   * Map Apollon relationship type back to SystemClassSpec relationship type.
   */
  private static reverseRelationshipType(apollonType: string): string {
    switch (apollonType) {
      case 'ClassInheritance':
        return 'Inheritance';
      case 'ClassComposition':
        return 'Composition';
      case 'ClassAggregation':
        return 'Aggregation';
      case 'ClassRealization':
        return 'Realization';
      case 'ClassDependency':
        return 'Dependency';
      case 'ClassBidirectional':
      case 'ClassUnidirectional':
      default:
        return 'Association';
    }
  }
}
