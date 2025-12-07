package com.fasterxml.jackson.databind.introspect;

import com.fasterxml.jackson.annotation.JsonFormat;
import com.fasterxml.jackson.databind.AnnotationIntrospector;
import com.fasterxml.jackson.databind.JavaType;
import com.fasterxml.jackson.databind.JsonMappingException;
import com.fasterxml.jackson.databind.PropertyMetadata;
import com.fasterxml.jackson.databind.PropertyName;
import com.fasterxml.jackson.databind.SerializerProvider;
import com.fasterxml.jackson.databind.cfg.MapperConfig;
import com.fasterxml.jackson.databind.jsonFormatVisitors.JsonObjectFormatVisitor;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.lang.annotation.Annotation;
import java.lang.reflect.AnnotatedElement;
import java.lang.reflect.Member;

import static org.hamcrest.MatcherAssert.assertThat;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

//TODO: Once mockito is updated to include Premain-Class in its MANIFEST.MF, we need to add -javaagent:/${m2directory}/.m2/repository/org/mockito/mockito-core/${mockit-version}/$33{mockit-version}.jar
class ConcreteBeanPropertyBaseTest {

    private static final class TestConcreteBeanPropertyBase extends ConcreteBeanPropertyBase {

        TestConcreteBeanPropertyBase(PropertyMetadata md) {
            super(md);
        }

        @Override
        public String getName() {
            return "";
        }

        @Override
        public PropertyName getFullName() {
            return null;
        }

        @Override
        public JavaType getType() {
            return null;
        }

        @Override
        public PropertyName getWrapperName() {
            return null;
        }

        @Override
        public <A extends Annotation> A getAnnotation(Class<A> acls) {
            return null;
        }

        @Override
        public <A extends Annotation> A getContextAnnotation(Class<A> acls) {
            return null;
        }

        @Override
        public AnnotatedMember getMember() {
            return new TestAnnotatedMember(null, null);
        }

        @Override
        public void depositSchemaProperty(JsonObjectFormatVisitor objectVisitor, SerializerProvider provider)
                throws JsonMappingException {

        }
    }

    private static final class TestAnnotatedMember extends AnnotatedMember {

        TestAnnotatedMember(TypeResolutionContext ctxt, AnnotationMap annotations) {
            super(ctxt, annotations);
        }

        @Override
        public Annotated withAnnotations(AnnotationMap fallback) {
            return null;
        }

        @Override
        public Class<?> getDeclaringClass() {
            return null;
        }

        @Override
        public Member getMember() {
            return null;
        }

        @Override
        public void setValue(Object pojo, Object value)
                throws UnsupportedOperationException, IllegalArgumentException {

        }

        @Override
        public Object getValue(Object pojo)
                throws UnsupportedOperationException, IllegalArgumentException {
            return null;
        }

        @Override
        public AnnotatedElement getAnnotated() {
            return null;
        }

        @Override
        protected int getModifiers() {
            return 0;
        }

        @Override
        public String getName() {
            return "";
        }

        @Override
        public JavaType getType() {
            return null;
        }

        @Override
        public Class<?> getRawType() {
            return null;
        }

        @Override
        public boolean equals(Object o) {
            return false;
        }

        @Override
        public int hashCode() {
            return 0;
        }

        @Override
        public String toString() {
            return "";
        }
    }

    private TestConcreteBeanPropertyBase testConcreteBeanProperty;
    private Class someType;
    private MapperConfig<?> mapperConfig;
    private AnnotationIntrospector annotationIntrospector;

    @BeforeEach
    void setUp() {
        mapperConfig = mock(MapperConfig.class);
        testConcreteBeanProperty =  new TestConcreteBeanPropertyBase(
                PropertyMetadata.STD_REQUIRED);
        annotationIntrospector = mock(AnnotationIntrospector.class);
        when(mapperConfig.getAnnotationIntrospector()).thenReturn(annotationIntrospector);
        someType = Class.class;
    }

    @Test
    void testFormatPrecedenceIsFollowed() {
        String lowestPrecedenceFormat = "Low Precedence";
        JsonFormat.Value midPrecedenceFormat = new JsonFormat.Value("Mid Precedence", null,
                (String) null, null, null, null);
        JsonFormat.Value highestPrecedence = new JsonFormat.Value("High Precedence", null,
                (String) null, null, null, null);
        when(mapperConfig.getDefaultRadix()).thenReturn(lowestPrecedenceFormat);
        when(mapperConfig.getDefaultPropertyFormat(any())).thenReturn(midPrecedenceFormat);
        when(annotationIntrospector.findFormat(any())).thenReturn(highestPrecedence);

        JsonFormat.Value resultFormat = testConcreteBeanProperty.findPropertyFormat(mapperConfig, someType);


        assertEquals(highestPrecedence.getPattern(), resultFormat.getPattern());
    }
}